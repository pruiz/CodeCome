CC ?= cc
CFLAGS ?= -Wall -Wextra -Wpedantic -O2 -Iinclude
LDFLAGS ?=

BIN_DIR := bin
SRC_DIR := src
OBJ_DIR := build
TARGET := $(BIN_DIR)/sample-c-cli

SRCS := $(SRC_DIR)/main.c $(SRC_DIR)/greet.c $(SRC_DIR)/util.c
OBJS := $(SRCS:$(SRC_DIR)/%.c=$(OBJ_DIR)/%.o)

.PHONY: all clean test

all: $(TARGET)

$(TARGET): $(OBJS)
	@mkdir -p $(BIN_DIR)
	$(CC) $(OBJS) $(LDFLAGS) -o $@

$(OBJ_DIR)/%.o: $(SRC_DIR)/%.c
	@mkdir -p $(OBJ_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

test: $(TARGET)
	./tests/smoke.sh

clean:
	rm -rf $(OBJ_DIR) $(BIN_DIR)
