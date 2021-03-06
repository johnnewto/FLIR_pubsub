# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/92_FLIR_server_utils.ipynb (unless otherwise specified).

__all__ = ['CameraThread', 'GPIOThread', 'register', 'server', 'PORT']

# Cell

# from  boxfish_stereo_cam.multipyspin import *
import FLIR_pubsub.multi_pyspin as multi_pyspin

import time
import zmq
import threading
import cv2
import imutils

try:
    import mraa
    use_mraa = True
except:
    use_mraa = False

# Cell

class CameraThread:
    '''
    Each camera is controlled by a separate thread, allowing it to be started stopped.
    When started the update loop will wait for a camera image and send it the  array data through a zmq socket.
    '''
    def __init__(self, socket_pub, i, yaml_dict, preview=False):
        self.stopped = True
        self.socket_pub = socket_pub
        self.i = i
        self.yaml_dict = yaml_dict
        self.preview = preview
        self.name = yaml_dict['name']
        self.serial = str(yaml_dict['serial'])
        self.encoding = yaml_dict['encoding']
        self.last_access = time.time()

    def send_array(self, A, flags=0, framedata=None, copy=True, track=False):
        """send a numpy array with metadata"""
        md = dict(
            dtype=str(A.dtype),
            shape=A.shape,
            framedata=framedata,
        )
        self.socket_pub.send_string(self.name, zmq.SNDMORE)
        self.socket_pub.send_json(md, flags | zmq.SNDMORE)
        return self.socket_pub.send(A, flags, copy=copy, track=track)

    def start(self):
        """
        Initialise and set camera thread and begin acquisition
        """
        self.thread = threading.Thread(target=self.update, args=(self.socket_pub, self.i, self.yaml_dict, ))
        self.thread.daemon = False
        self.stopped = False
        self.thread.start()
        return self

    def stop(self):
        """indicate that the thread should be stopped"""
        self.stopped = True
        # wait until stream resources are released (producer thread might be still grabbing frame)
        self.thread.join()

    def update(self, socket, cam_num, yaml_dict):
        # Prepare publisher

        multi_pyspin.init(self.serial)
        multi_pyspin.start_acquisition(self.serial)
        print(f'Starting : {self.name}')
        i = 0
        while True:
            i += 1

            # cam = multi_pyspin._get_cam(serial)
            # image = cam.GetNextImage()
            try:
                image, image_dict = multi_pyspin.get_image(self.serial)
                img = image.GetNDArray()
                shape = img.shape
                if self.encoding is not None:
                    img = cv2.imencode(self.encoding, img)[1]  # i.e encode into jpeg

                md = {'frameid': i, 'encoding': self.encoding, 'size': img.size, 'shape': shape}
                self.send_array( img, framedata=md)
            except Exception as e:
                print(str(e))


            if self.preview:
                if self.encoding is not None:
                    _frame = cv2.imdecode(img, cv2.IMREAD_GRAYSCALE)
                else:
                    _frame = img

                _frame = cv2.cvtColor(_frame, cv2.COLOR_BAYER_BG2BGR)
                _frame = imutils.resize(_frame, width=1000, height=750)
                cv2.imshow(self.name, _frame)
                cv2.waitKey(10)

            if time.time() - self.last_access > 10:
                print(f'Stopping {self.name} due to inactivity.')
                self.stopped = True

            if self.stopped:
                break


        multi_pyspin.end_acquisition(self.serial)
        multi_pyspin.deinit(self.serial)

# Cell
class GPIOThread:
    '''
    A thread class to control and toggle Upboard GPIO pins, allowing it to be started & stopped.
    Pin number and frequency can be set
    '''
    def __init__(self, pin_no, freq=2.0):
        self.stopped = True
        # Export the GPIO pin for use
        if use_mraa:
            self.pin = mraa.Gpio(pin_no)
            self.pin.dir(mraa.DIR_OUT)
            self.pin.write(0)
        self.period = 1 / (2 * freq)

    def start(self):
        """Start the pin toggle"""
        self.thread = threading.Thread(target=self.update, args=())
        self.thread.daemon = False
        self.stopped = False
        self.thread.start()
        return self

    def stop(self):
        """Stop the pin toggle"""
        self.stopped = True
        # wait until stream resources are released (producer thread might be still grabbing frame)
        self.thread.join()

    def update(self):
        # Loop
        while True:
            if use_mraa:
                self.pin.write(1)
            # else:
            #     print('1', end='')
            time.sleep(self.period)
            if use_mraa:
                self.pin.write(0)
            # else:
            #     print('0')
            time.sleep(self.period)
            if self.stopped:
                break

# Cell
PORT = 5555

def register():
    """Run multi_pyspin constructor and register multi_pyspin destructor. Should be called once when first imported"""
    multi_pyspin.register()

def server(yaml_dir):
    """
    Main loop for the server. Polls and sets up the cameras. Sets up the socket and port numbers and starts threads.
    """



    # # Install cameras
    pub_threads = []
    yaml_dicts = []
    for i, serial in enumerate(list(multi_pyspin.SERIAL_DICT)):
        print(f'{yaml_dir/serial}.yaml')
        yaml_dict = multi_pyspin.setup(f'{yaml_dir/serial}.yaml')
        yaml_dicts.append(yaml_dict)

    # yaml_dir=Path('common')
    # # # Install cameras
    # pub_threads = []
    # yaml_dicts = []
    # for i, serial in enumerate(list(multi_pyspin.SERIAL_DICT)):
    #     yaml_dict = multi_pyspin.setup(f'{yaml_dir/serial}.yaml')
    #     yaml_dicts.append(yaml_dict)


    context = zmq.Context()
    socket_pub = context.socket(zmq.PUB)
    socket_pub.setsockopt(zmq.SNDHWM, 20)
    socket_pub.setsockopt(zmq.LINGER, 0)
    # socket_pub.setsockopt(zmq.SO_REUSEADDR, 1)
    socket_pub.bind(f"tcp://*:{PORT}")

    socket_rep = context.socket(zmq.REP)
    socket_rep.RCVTIMEO = 1000
    socket_rep.bind(f"tcp://*:{PORT+1}")

    for i, yaml_dict in enumerate(list(yaml_dicts)):
        ct = CameraThread(socket_pub, i, yaml_dict)
        ct.start()
        pub_threads.append(ct)

    gpio1 = GPIOThread(29, 2.0).start()
    gpio2 = GPIOThread(31, 10.0).start()
    while True:
        try:
            message = socket_rep.recv().decode("utf-8")
            socket_rep.send_string("OK")
            name = message.split()[1]
            pt = [pt for pt in pub_threads if pt.name == name]
            if len(pt) == 1:
                pt[0].last_access = time.time()
                if pt[0].stopped:
                    pt[0].start()

        except zmq.error.Again:
            pass

        except KeyboardInterrupt:
            break

        except Exception as e:
            print(str(e))

    for ct in pub_threads:
        print(f"stopping {ct.name}")
        ct.stop()

    gpio1.stop()
    gpio2.stop()
    cv2.destroyAllWindows()
    socket_pub.close()
    socket_rep.close()
    context.term()

if __name__ == '__main__':
    import sys
    from pathlib import Path

    sys.path.append(str(Path.cwd()))

    register()
    yaml_dir = Path.cwd() / '../nbs/common'
    print(f'yaml_dir {yaml_dir}')
    server(yaml_dir)