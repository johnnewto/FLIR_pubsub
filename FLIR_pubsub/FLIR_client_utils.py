# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/93_FLIR_client_utils.ipynb (unless otherwise specified).

__all__ = ['FLIR_Client', 'PORT', 'client', 'width', 'height', 'stereo_client']

# Cell

import imutils
import cv2
from imutils.video import FPS
import zmq
import numpy as np
import time
import skvideo.io


PORT = 5555

class FLIR_Client:
    ''' Connect to an FLIR ZMQ publisher server via a ZMQ subscribe sockets and receiver FLIR camer frames'''
    def __init__(self, name='FrontLeft', url='localhost'):
        self.name = name
        self.url = url
        self.context = zmq.Context()
        # subscribe socket
        print("Connecting to server...")
        self.socket = self.context.socket(zmq.SUB)
        self.socket.connect(f"tcp://{url}:{PORT}")
        self.socket.setsockopt_string(zmq.SUBSCRIBE, name)
        self.fps = FPS().start()

    def recv_array(self, flags=0, copy=True, track=False):
        """recv a numpy array"""
        md = self.socket.recv_json(flags=flags)
        msg = self.socket.recv(flags=flags, copy=copy, track=track)
        buf = memoryview(msg)
        A = np.frombuffer(buf, dtype=md['dtype'])
        # return (A.reshape(md['shape']), md)
        return (A, md)

    def recv_frame(self):
        """ Receive and process an image from camera"""
        try:
            #  Get the reply.
            topic = self.socket.recv_string()
            rec_frame, md = self.recv_array()
            rec_frame = cv2.imdecode(rec_frame, cv2.IMREAD_GRAYSCALE)
            rec_frame = cv2.cvtColor(rec_frame, cv2.COLOR_BAYER_BG2BGR)
            (height, width) = md['framedata']['shape']
            rec_frame.shape = (height, width, 3)
            # rec_frame = rec_frame.reshape((height, width, 3))

            # rec_frame = imutils.resize(rec_frame, width=width, height=height)
            # cv2.putText(rec_frame, f'Received frame {md}',
            #             (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            if self.fps is not None:
                self.fps.update()

        except Exception as e:
            rec_frame = np.ones((1000,750))
            topic = 'cam1'
            md = None
            # cv2.putText(rec_frame, f'error:  {e}',
            #             (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            print (f"error: message timeout {e}")
            time.sleep(1)
        return topic, rec_frame, md


    def poll_server(self,):
        """ poll the server periodically to keep it sending frames,
        if you stop polling the server will timeout to save bandwidth and server CPU"""
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect(f"tcp://{self.url}:{PORT + 1}")
        socket.setsockopt(zmq.LINGER, 0)
        poller = zmq.Poller()
        poller.register(socket, flags=zmq.POLLIN)

        socket.send_string(f"keep_alive {self.name}")
        socks = dict(poller.poll(1000))
        if socket in socks and socks[socket] == zmq.POLLIN:
            message = socket.recv() # server should return 'ok'
            ret = True
        else:
            ret = False
        poller.unregister(socket)
        return ret

    def close(self):
        self.socket.close()
        self.context.term()
        self.fps.stop()

    def read_image(self):
        frame, topic, md  = None, None, None
        try:
            # find server  and tell stay alive
            if self.poll_server():
                topic, frame, md = self.recv_frame()
            else:
                raise TimeoutError(f'Server {self.url} : {self.name} timeout')
        except TimeoutError as err:
            print(err.args)
        except Exception as err:
            print(err.args)
        finally:
            return frame, topic, md

# def poll_server(socket, poller, name):
#     """ poll the server periodically to keep it sending frames,
#     if you stop polling the server will timeout to save bandwidth and server CPU"""
#     socket.send_string(f"keep_alive {name}")
#     socks = dict(poller.poll(1000))
#     if socket in socks and socks[socket] == zmq.POLLIN:
#         message = socket.recv()
#         return True
#     else:
#         return False

# Cell
width = 1000
height = 750
def client(name='FrontLeft', url='localhost'):
    """ Received frames from a single camera. Must have the server running"""
    # cv2.namedWindow(name)
    chan = FLIR_Client(name=name, url=url)
    i = 0
    while True:
        try:
            frame, topic, md = chan.read_image()

        except KeyboardInterrupt:
            break
        k = cv2.waitKey(10)
        if k == 27 or k == 3:
           break  # esc to quit

        if frame is not None:
            frame = imutils.resize(frame, width=width, height=height)
            cv2.putText(frame, f"{md['framedata']['frameid']}",
                        (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 3, (255, 255, 255), 5)
            cv2.imshow(topic, frame)

            txt = None
            if k == ord('c'):
                i = 0
                txt = f'Reset name to {topic}-{i}.jpg'
            elif k >= ord('s'):
                txt = f'Saving {topic}-{i}.jpg'
                cv2.imwrite(f'{topic}-{i}.jpg', frame)
                i += 1
            if txt is not None:
                print(txt)
                cv2.putText(frame, txt, (100, 500), cv2.FONT_HERSHEY_SIMPLEX, 3, (255, 255, 255), 5)
                cv2.imshow(topic, frame)
                cv2.waitKey(1000)

    chan.close()
    cv2.destroyAllWindows()

    print('Finished')
    print("[INFO] approx. FPS: {:.2f}".format(chan.fps.fps()))

# Cell


def stereo_client(name1='FrontLeft', name2='FrontRight', url='localhost', video=None, vcodec='mjpeg'):
    """ Received frames from two cameras. Must have the server running"""
    chan1 = FLIR_Client(name=name1, url=url)
    chan2 = FLIR_Client(name=name2, url=url)

    writer = None
    if video is not None:
        writer = skvideo.io.FFmpegWriter(video, outputdict={'-vcodec': 'mjpeg'})
        # writer = skvideo.io.FFmpegWriter(outputfile, outputdict={'-vcodec': 'libx264', '-b': '30000000', '-r': "2"})

    SHOW_CV_WINDOW = True

    while True:
        try:
            frame1, topic1, md1 = chan1.read_image()
            frame2, topic2, md1 = chan1.read_image()


            if writer is not None:
                if frame1.shape == frame2.shape:
                    concat_frame = np.concatenate((frame1, frame2), axis=1)
                    writer.writeFrame(concat_frame)
                    print(f"Writing Frame pair {topic1}, {topic2}")
                else:
                    print(f"frames shapes are different, {name1}: {frame1.shape} {name2}: {frame2.shape} ")

            if SHOW_CV_WINDOW:
                if frame1 is not None:
                    sframe1 = imutils.resize(frame1, width=width, height=height)
                    cv2.imshow(topic1, sframe1)

                if frame2 is not None:
                    sframe2 = imutils.resize(frame2, width=width, height=height)
                    cv2.imshow(topic2, sframe2)

                k = cv2.waitKey(10)
                if k == 27 or k == 3:
                    break

        except KeyboardInterrupt:
            break

    chan1.close()
    chan2.close()
    if writer is not None: writer.close()

    cv2.destroyAllWindows()

    print('Finished')
    print("[INFO] Chan1 approx. FPS: {:.2f}".format(chan1.fps.fps()))
    print("[INFO] Chan1 approx. FPS: {:.2f}".format(chan1.fps.fps()))


# Cell
#export
if __name__ == '__main__':

    client(name='FrontLeft', url='localhost')
    stereo_client(name1='FrontLeft', name2='FrontRight', url='localhost', video=None, vcodec='mjpeg')