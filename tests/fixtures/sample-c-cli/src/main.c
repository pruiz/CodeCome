#include <stdio.h>
#include <string.h>

#include "greet.h"

static void print_help(void) {
    puts("sample-c-cli commands:");
    puts("  greet <name>");
    puts("  echo <message>");
    puts("  remove <path>");
}

int main(int argc, char **argv) {
    if (argc < 2) {
        print_help();
        return 1;
    }

    if (strcmp(argv[1], "--help") == 0) {
        print_help();
        return 0;
    }

    if (strcmp(argv[1], "greet") == 0 && argc >= 3) {
        greet_user(argv[2]);
        return 0;
    }

    if (strcmp(argv[1], "echo") == 0 && argc >= 3) {
        echo_message(argv[2]);
        return 0;
    }

    if (strcmp(argv[1], "remove") == 0 && argc >= 3) {
        return remove_file(argv[2]);
    }

    print_help();
    return 1;
}
