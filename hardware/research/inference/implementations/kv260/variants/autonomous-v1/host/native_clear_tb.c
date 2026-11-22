/* Run actual portable host code against the existing synthetic MMIO fixture. */
#define main existing_host_main
#include "host_tb.c"
#undef main

int main(void)
{
    struct mock hardware;
    struct fpga_host native;
    struct fpga_host_frame frame;
    CHECK(existing_host_main() == 0);
    CHECK(configured(&hardware, &native) == FPGA_HOST_OK);
    CHECK(fpga_host_step(&native, 256, &frame, long_deadline) == FPGA_HOST_OK);

    /* An AU01 request advanced hardware without issuing native step calls. */
    hardware.count = 101;
    CHECK(native.context_count == 1 && native.state == FPGA_HOST_READY);
    CHECK(fpga_host_clear_context(&native, long_deadline) == FPGA_HOST_OK);
    CHECK(hardware.count == 0 && native.context_count == 0 &&
          native.logits_received == 0 && hardware.clear_writes == 1);
    hardware.count = 256;
    CHECK(fpga_host_clear_context(&native, long_deadline) == FPGA_HOST_OK);
    CHECK(hardware.count == 0 && native.context_count == 0 && hardware.clear_writes == 2);
    CHECK(fpga_host_step(&native, 256, &frame, long_deadline) == FPGA_HOST_OK);
    CHECK(frame.received == 320 && native.context_count == 1);
    CHECK(hardware.model_words == 29281 && hardware.reset_writes == 1);
    puts("PASS sealed portable host clear after independently advanced AU01 context");
    return 0;
}
