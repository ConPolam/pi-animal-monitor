CC = gcc
CFLAGS = -O2 -Wall
LIBS = -ljpeg
SRCDIR = src
SRC = $(SRCDIR)/capture.c $(SRCDIR)/yuyv_to_jpeg.c $(SRCDIR)/client_send.c
TARGET = cam_sender

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -o $(TARGET) $(SRC) $(LIBS) -lm

clean:
	rm -f $(TARGET)
