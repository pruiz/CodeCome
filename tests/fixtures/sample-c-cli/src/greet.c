#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "greet.h"
#include "util.h"

void greet_user(const char *name) {
    char buffer[32];
    size_t copy_len = clamp_copy_length(name, sizeof(buffer));

    memcpy(buffer, name, copy_len);
    buffer[copy_len] = '\0';

    printf("Hello, %s\n", buffer);
}

void echo_message(const char *message) {
    printf(message);
    putchar('\n');
}

int remove_file(const char *path) {
    char command[256];

    snprintf(command, sizeof(command), "rm -f %s", path);
    return system(command);
}
