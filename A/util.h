#ifndef UTIL_H
#define UTIL_H

#include <stddef.h>

struct buffer {
    void   *start;
    size_t length;
};

int open_cam(const char *dev);
int set_format(int fd, int width, int height);
int init_mmap(int fd, struct buffer **buffers, int *buf_count);
int read_frame(int fd, struct buffer *buffers, int buf_count, void **out_ptr, int *out_len);
void close_cam(int fd, struct buffer *buffers, int buf_count);

int yuyv_to_jpeg(unsigned char *yuyv, int width, int height,
                 unsigned char **jpegBuf, unsigned long *jpegSize, int quality);

#endif
