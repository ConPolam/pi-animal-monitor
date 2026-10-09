// client_send.c
#include "util.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <signal.h>
#include <time.h>

#define DEVICE "/dev/video0"
#define WIDTH 640
#define HEIGHT 480
#define QUALITY 75
#define PORT 5000

static int server_fd = -1;
static int cam_fd = -1;
static struct buffer *buffers = NULL;
static int buf_count = 0;
static volatile int running = 1;

void sigint_handler(int s) {
    running = 0;
}

int start_server(int port) {
    int sfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sfd < 0) { perror("socket"); return -1; }
    int opt = 1;
    setsockopt(sfd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    struct sockaddr_in addr;
    memset(&addr,0,sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(port);
    if (bind(sfd, (struct sockaddr*)&addr, sizeof(addr)) < 0) { perror("bind"); close(sfd); return -1; }
    if (listen(sfd, 1) < 0) { perror("listen"); close(sfd); return -1; }
    return sfd;
}

int send_all(int sock, unsigned char *buf, size_t len) {
    size_t total = 0;
    while (total < len) {
        ssize_t sent = send(sock, buf + total, len - total, 0);
        if (sent <= 0) return -1;
        total += sent;
    }
    return 0;
}

int handle_connection(int conn) {
    char cmdbuf[32];
    int sending = 0;
    struct timespec ts = {0, 100 * 1000 * 1000}; // 100 ms -> ~10 fps

    while (running) {
        // non-blocking recv of command (peek)
        ssize_t r = recv(conn, cmdbuf, sizeof(cmdbuf)-1, MSG_DONTWAIT);
        if (r > 0) {
            cmdbuf[r] = 0;
            // trim newline
            char *p = strchr(cmdbuf, '\n'); if (p) *p = 0;
            printf("Received command: %s\n", cmdbuf);

            
            if (strncmp(cmdbuf, "TAKE", 4) == 0) {
                 printf("Processing TAKE command...\n");  // 添加这行调试信息
    // 暂停视频流发送
    int was_sending = sending;
    sending = 0;
    
    // 短暂等待确保视频流停止
    struct timespec wait = {0, 100 * 1000 * 1000}; // 100ms
    nanosleep(&wait, NULL);
    
    // 抓拍一帧
    void *ptr; int len;
    if (read_frame(cam_fd, buffers, buf_count, &ptr, &len) == 0) {
        unsigned char *jpegBuf = NULL; unsigned long jpegSize = 0;
        if (yuyv_to_jpeg(ptr, WIDTH, HEIGHT, &jpegBuf, &jpegSize, QUALITY) == 0) {
            uint32_t netlen = htonl((uint32_t)jpegSize);
            if (send_all(conn, (unsigned char*)&netlen, 4) < 0) { 
                free(jpegBuf); 
                sending = was_sending; // 恢复状态
                return -1; 
            }
            if (send_all(conn, jpegBuf, jpegSize) < 0) { 
                free(jpegBuf); 
                sending = was_sending; // 恢复状态
                return -1; 
            }
            printf("Sent TAKE frame %lu bytes\n", jpegSize);
            free(jpegBuf);
        }
    }
    
    // 恢复原来的发送状态
    sending = was_sending;
}

else if (strncmp(cmdbuf, "START", 5) == 0) {
                       sending = 1;
                  } else if (strncmp(cmdbuf, "STOP", 4) == 0) {
                      sending = 0;
                   } else {
                           printf("Unknown cmd: %s\n", cmdbuf);
                  }
              }

        if (sending) {
            void *ptr; int len;
            int rc = read_frame(cam_fd, buffers, buf_count, &ptr, &len);
            if (rc == 0) {
                unsigned char *jpegBuf = NULL; unsigned long jpegSize = 0;
                if (yuyv_to_jpeg(ptr, WIDTH, HEIGHT, &jpegBuf, &jpegSize, QUALITY) == 0) {
                    uint32_t netlen = htonl((uint32_t)jpegSize);
                    if (send_all(conn, (unsigned char*)&netlen, 4) < 0) { free(jpegBuf); return -1; }
                    if (send_all(conn, jpegBuf, jpegSize) < 0) { free(jpegBuf); return -1; }
                    free(jpegBuf);
                }
            } else if (rc == 1) {
                // no frame yet, just wait a bit
            } else {
                return -1;
            }
            // frame rate control
            nanosleep(&ts, NULL);
        } else {
            // idle, small sleep
            struct timespec t = {0, 50 * 1000 * 1000};
            nanosleep(&t, NULL);
        }
    }
    return 0;
}

int main(int argc, char **argv) {
    signal(SIGINT, sigint_handler);
    // open camera
    cam_fd = open_cam(DEVICE);
    if (cam_fd < 0) { fprintf(stderr, "open camera failed\n"); return -1; }
    if (set_format(cam_fd, WIDTH, HEIGHT) < 0) { fprintf(stderr, "set format failed\n"); return -1; }
    if (init_mmap(cam_fd, &buffers, &buf_count) < 0) { fprintf(stderr, "init mmap failed\n"); return -1; }
    printf("Camera initialized (%dx%d)\n", WIDTH, HEIGHT);

    server_fd = start_server(PORT);
    if (server_fd < 0) { fprintf(stderr, "start server failed\n"); return -1; }
    printf("Listening on port %d\n", PORT);

    while (running) {
        struct sockaddr_in client_addr;
        socklen_t clilen = sizeof(client_addr);
        int conn = accept(server_fd, (struct sockaddr*)&client_addr, &clilen);
        if (conn < 0) {
            perror("accept");
            break;
        }
        char ipbuf[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &client_addr.sin_addr, ipbuf, sizeof(ipbuf));
        printf("Client connected: %s\n", ipbuf);
        int rc = handle_connection(conn);
        close(conn);
        if (rc < 0) {
            printf("Connection closed with error\n");
        } else {
            printf("Connection closed\n");
        }
    }

    close_cam(cam_fd, buffers, buf_count);
    if (server_fd >= 0) close(server_fd);
    return 0;
}
