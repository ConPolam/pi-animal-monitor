// capture.c
#include "util.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/videodev2.h>
#include <errno.h>

int open_cam(const char *dev) {
    int fd = open(dev, O_RDWR | O_NONBLOCK, 0);
    if (fd < 0) {
        perror("open");
        return -1;
    }
    return fd;
}

int set_format(int fd, int width, int height) {
    struct v4l2_format fmt;
    memset(&fmt, 0, sizeof(fmt));
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width = width;
    fmt.fmt.pix.height = height;
    fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_YUYV; // YUYV
    fmt.fmt.pix.field = V4L2_FIELD_NONE;
    if (ioctl(fd, VIDIOC_S_FMT, &fmt) < 0) {
        perror("VIDIOC_S_FMT");
        return -1;
    }
    return 0;
}

int init_mmap(int fd, struct buffer **buffers, int *buf_count) {
    struct v4l2_requestbuffers req;
    memset(&req,0,sizeof(req));
    req.count = 4;
    req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory = V4L2_MEMORY_MMAP;
    if (ioctl(fd, VIDIOC_REQBUFS, &req) < 0) {
        perror("VIDIOC_REQBUFS");
        return -1;
    }

    *buf_count = req.count;
    *buffers = calloc(req.count, sizeof(struct buffer));
    if (!*buffers) return -1;

    for (int i=0;i<req.count;i++) {
        struct v4l2_buffer buf;
        memset(&buf,0,sizeof(buf));
        buf.type = req.type;
        buf.memory = V4L2_MEMORY_MMAP;
        buf.index = i;
        if (ioctl(fd, VIDIOC_QUERYBUF, &buf) < 0) {
            perror("VIDIOC_QUERYBUF");
            return -1;
        }
        (*buffers)[i].length = buf.length;
        (*buffers)[i].start = mmap(NULL, buf.length, PROT_READ|PROT_WRITE, MAP_SHARED, fd, buf.m.offset);
        if ((*buffers)[i].start == MAP_FAILED) {
            perror("mmap");
            return -1;
        }
        if (ioctl(fd, VIDIOC_QBUF, &buf) < 0) {
            perror("VIDIOC_QBUF");
            return -1;
        }
    }
    int type = req.type;
    if (ioctl(fd, VIDIOC_STREAMON, &type) < 0) {
        perror("VIDIOC_STREAMON");
        return -1;
    }
    return 0;
}

int read_frame(int fd, struct buffer *buffers, int buf_count, void **out_ptr, int *out_len) {
    struct v4l2_buffer buf;
    memset(&buf,0,sizeof(buf));
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    if (ioctl(fd, VIDIOC_DQBUF, &buf) < 0) {
        if (errno == EAGAIN) return 1; // no frame yet
        perror("VIDIOC_DQBUF");
        return -1;
    }
    *out_ptr = buffers[buf.index].start;
    *out_len = buf.bytesused;
    if (ioctl(fd, VIDIOC_QBUF, &buf) < 0) {
        perror("VIDIOC_QBUF requeue");
        return -1;
    }
    return 0;
}

void close_cam(int fd, struct buffer *buffers, int buf_count) {
    int type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    ioctl(fd, VIDIOC_STREAMOFF, &type);
    for (int i=0;i<buf_count;i++) {
        munmap(buffers[i].start, buffers[i].length);
    }
    free(buffers);
    close(fd);
}
