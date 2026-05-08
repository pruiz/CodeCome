#include <string.h>

#include "util.h"

size_t clamp_copy_length(const char *input, size_t max_len) {
    size_t length = strlen(input);

    if (length > max_len) {
        return max_len;
    }

    return length;
}
