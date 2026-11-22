/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */
#ifndef KV260_DDR4_UAPI_H
#define KV260_DDR4_UAPI_H

#include <linux/ioctl.h>
#include <linux/types.h>

#define KV260_DDR4_BYTES 2048U
#define KV260_DDR4_SAFE_RELEASE (1U << 3)
#define KV260_DDR4_ENABLED (1U << 0)
#define KV260_DDR4_BUSY (1U << 1)
#define KV260_DDR4_FAULT (1U << 2)
#define KV260_DDR4_MODE_SHIFT 5U
#define KV260_DDR4_MODE_MASK (3U << KV260_DDR4_MODE_SHIFT)

struct kv260_ddr4_state {
    __u32 dma_base;
    __u32 dma_bytes;
    __u32 hardware_base;
    __u32 status;
    __u32 useful_bytes;
    __u32 reads;
    __u32 beats;
    __u32 faults;
    __u32 extra_clocks;
    __u32 ar_stalls;
    __u32 response_wait;
    __u32 projection_count;
    __u32 projection_clocks;
    __u32 magic;
};

#define KV260_DDR4_STATE _IOR('W', 0, struct kv260_ddr4_state)
#define KV260_DDR4_BRAM _IO('W', 1)
#define KV260_DDR4_SCALAR _IO('W', 2)
#define KV260_DDR4_CLEAR _IO('W', 3)
#define KV260_DDR4_BEAT _IO('W', 4)
#define KV260_DDR4_ROW _IO('W', 5)

#endif
