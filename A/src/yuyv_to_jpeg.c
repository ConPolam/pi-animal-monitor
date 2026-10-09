// yuyv_to_jpeg.c
#include "util.h"
#include <stdio.h>
#include <stdlib.h>
#include <jpeglib.h>

static inline void yuyv_to_rgb_row(unsigned char *yuyv, unsigned char *rgb, int width) {
    // yuyv: [Y0 U0 Y1 V0] ...
    for (int x = 0; x < width; x += 2) {
        int y0 = yuyv[0];
        int u  = yuyv[1];
        int y1 = yuyv[2];
        int v  = yuyv[3];

        int c = y0 - 16;
        int d = u - 128;
        int e = v - 128;
        int r = (298 * c + 409 * e + 128) >> 8;
        int g = (298 * c - 100 * d - 208 * e + 128) >> 8;
        int b = (298 * c + 516 * d + 128) >> 8;
        if (r < 0) r = 0; if (r > 255) r = 255;
        if (g < 0) g = 0; if (g > 255) g = 255;
        if (b < 0) b = 0; if (b > 255) b = 255;
        rgb[0]=r; rgb[1]=g; rgb[2]=b;

        c = y1 - 16;
        r = (298 * c + 409 * e + 128) >> 8;
        g = (298 * c - 100 * d - 208 * e + 128) >> 8;
        b = (298 * c + 516 * d + 128) >> 8;
        if (r < 0) r = 0; if (r > 255) r = 255;
        if (g < 0) g = 0; if (g > 255) g = 255;
        if (b < 0) b = 0; if (b > 255) b = 255;
        rgb[3]=r; rgb[4]=g; rgb[5]=b;

        yuyv += 4;
        rgb += 6;
    }
}

int yuyv_to_jpeg(unsigned char *yuyv, int width, int height,
                 unsigned char **jpegBuf, unsigned long *jpegSize, int quality) {
    // allocate RGB buffer for one row at a time to save memory
    JSAMPARRAY image_buffer = NULL;
    struct jpeg_compress_struct cinfo;
    struct jpeg_error_mgr jerr;

    cinfo.err = jpeg_std_error(&jerr);
    jpeg_create_compress(&cinfo);

    unsigned char *outbuffer = NULL;
    unsigned long outsize = 0;
    jpeg_mem_dest(&cinfo, &outbuffer, &outsize);

    cinfo.image_width = width;
    cinfo.image_height = height;
    cinfo.input_components = 3;
    cinfo.in_color_space = JCS_RGB;
    jpeg_set_defaults(&cinfo);
    jpeg_set_quality(&cinfo, quality, TRUE);

    jpeg_start_compress(&cinfo, TRUE);

    int row_stride = width * 3;
    unsigned char *rgb_row = malloc(row_stride);
    if (!rgb_row) {
        jpeg_destroy_compress(&cinfo);
        return -1;
    }

    unsigned char *yuyv_ptr = yuyv;
    while (cinfo.next_scanline < cinfo.image_height) {
        // convert one row: YUYV has 2 pixels per 4 bytes; bytes per row = width*2
        unsigned char *yuyv_row = yuyv_ptr + (cinfo.next_scanline * width * 2);
        yuyv_to_rgb_row(yuyv_row, rgb_row, width);
        JSAMPROW row_pointer[1];
        row_pointer[0] = rgb_row;
        jpeg_write_scanlines(&cinfo, row_pointer, 1);
    }

    free(rgb_row);
    jpeg_finish_compress(&cinfo);
    jpeg_destroy_compress(&cinfo);

    *jpegBuf = outbuffer;
    *jpegSize = outsize;
    return 0;
}
