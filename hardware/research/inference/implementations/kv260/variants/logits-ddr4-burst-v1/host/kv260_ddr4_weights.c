// SPDX-License-Identifier: GPL-2.0
#include <linux/dma-mapping.h>
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/iommu.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of_address.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include <linux/uaccess.h>

#include "kv260_ddr4_uapi.h"

#define MODEL_STATUS 0xa0000000
#define MODEL_BUSY BIT(1)
#define MMIO_BASE 0xa0000060
#define REG_BASE 0x00
#define REG_CONTROL 0x04
#define REG_USEFUL_BYTES 0x08
#define REG_READS 0x0c
#define REG_BEATS 0x10
#define REG_FAULTS 0x14
#define REG_EXTRA_CLOCKS 0x18
#define REG_AR_STALLS 0x1c
#define REG_RESPONSE_WAIT 0x20
#define REG_PROJECTION_COUNT 0x24
#define REG_PROJECTION_CLOCKS 0x28
#define REG_FIXTURE 0x2c
#define FIXTURE_ID 0x44445233
#define DDR_LIMIT 0x80000000ULL
#define WEIGHTS_ORDER get_order(KV260_DDR4_BYTES)
#define HP0_STREAM_ID 0xe80

/* One accelerator instance. State survives fd close and failed teardown. */
static DEFINE_MUTEX(fixture_lock);
static struct device *fixture_dev;
static void __iomem *regs;
static void __iomem *model_status;
static struct page *weights;
static dma_addr_t weights_dma;
static bool opened;
static bool translated;

static int reject_other_group_member(struct device *member, void *expected)
{
    return member == expected ? 0 : -EBUSY;
}

static int check_dma_domain(struct device *dev)
{
    struct iommu_group *group;
    struct iommu_domain *domain;
    int ret;

    domain = iommu_get_domain_for_dev(dev);
    if (!domain || !(domain->type & __IOMMU_DOMAIN_DMA_API))
        return -EINVAL;
    group = iommu_group_get(dev);
    if (!group)
        return -ENODEV;
    ret = iommu_group_for_each_dev(group, dev, reject_other_group_member);
    iommu_group_put(group);
    return ret;
}

static int check_dma_path(struct device *dev, bool *uses_iommu)
{
    struct device_node *smmu;
    struct of_phandle_args stream;
    bool direct;
    int ret;

    if (of_dma_is_coherent(dev->of_node))
        return -EINVAL;

    direct = of_property_read_bool(dev->of_node, "gradiated,verified-direct-dma");
    if (direct) {
        smmu = of_find_compatible_node(NULL, NULL, "arm,mmu-500");
        if (!smmu)
            return -ENODEV;
        ret = of_device_is_available(smmu) ? -EINVAL : 0;
        of_node_put(smmu);
        if (ret || device_iommu_mapped(dev) ||
            of_property_present(dev->of_node, "iommus"))
            return -EINVAL;
    } else {
        if (of_count_phandle_with_args(dev->of_node, "iommus",
                                       "#iommu-cells") != 1)
            return -EINVAL;
        ret = of_parse_phandle_with_args(dev->of_node, "iommus",
                                        "#iommu-cells", 0, &stream);
        if (ret)
            return ret;
        if (!of_device_is_compatible(stream.np, "arm,mmu-500") ||
            !of_device_is_available(stream.np) || stream.args_count != 1 ||
            stream.args[0] != HP0_STREAM_ID)
            ret = -EINVAL;
        of_node_put(stream.np);
        if (ret)
            return ret;
        ret = check_dma_domain(dev);
        if (ret)
            return ret;
    }
    *uses_iommu = !direct;
    return 0;
}

static bool correct_fixture(void)
{
    return readl(regs + REG_FIXTURE) == FIXTURE_ID;
}

static bool safe_release(void)
{
    const u32 mask = KV260_DDR4_SAFE_RELEASE | KV260_DDR4_ENABLED |
                     KV260_DDR4_BUSY;

    return (readl(regs + REG_CONTROL) & mask) == KV260_DDR4_SAFE_RELEASE;
}

static bool device_idle(void)
{
    /* The supervisor serializes UIO inference starts with DDR control. */
    return !(readl(model_status) & MODEL_BUSY) &&
           !(readl(regs + REG_CONTROL) & KV260_DDR4_BUSY);
}

static bool within_ddr_window(u64 base)
{
    return base && IS_ALIGNED(base, 64) && base <= DDR_LIMIT - KV260_DDR4_BYTES;
}

static int weights_open(struct inode *inode, struct file *file)
{
    int ret = 0;

    mutex_lock(&fixture_lock);
    if (!fixture_dev)
        ret = -ENODEV;
    else if (opened)
        ret = -EBUSY;
    else
        opened = true;
    mutex_unlock(&fixture_lock);
    return ret;
}

static int weights_close(struct inode *inode, struct file *file)
{
    mutex_lock(&fixture_lock);
    opened = false;
    mutex_unlock(&fixture_lock);
    return 0;
}

static ssize_t weights_write(struct file *file, const char __user *user,
                             size_t count, loff_t *position)
{
    dma_addr_t address;
    struct page *page;
    void *image;
    ssize_t ret;

    if (count != KV260_DDR4_BYTES)
        return -EMSGSIZE;
    image = memdup_user(user, count);
    if (IS_ERR(image))
        return PTR_ERR(image);

    mutex_lock(&fixture_lock);
    if (!fixture_dev || !correct_fixture()) {
        ret = -ENODEV;
        goto out_unlock;
    }
    if (weights || !device_idle() || !safe_release() ||
        readl(regs + REG_BASE)) {
        ret = -EBUSY;
        goto out_unlock;
    }

    if (translated) {
        ret = check_dma_domain(fixture_dev);
        if (ret)
            goto out_unlock;
    }
    /* Contiguous private pages. DMA32 selects the low DDR bank. */
    page = alloc_pages(GFP_KERNEL | GFP_DMA32 | __GFP_ZERO, WEIGHTS_ORDER);
    if (!page) {
        ret = -ENOMEM;
        goto out_unlock;
    }
    if (!translated && !within_ddr_window(page_to_phys(page))) {
        __free_pages(page, WEIGHTS_ORDER);
        ret = -ERANGE;
        goto out_unlock;
    }
    memcpy(page_address(page), image, count);
    address = dma_map_single(fixture_dev, page_address(page), count, DMA_TO_DEVICE);
    if (dma_mapping_error(fixture_dev, address)) {
        __free_pages(page, WEIGHTS_ORDER);
        ret = -EIO;
        goto out_unlock;
    }
    if (!within_ddr_window(address) ||
        (!translated && address != page_to_phys(page))) {
        dma_unmap_single(fixture_dev, address, count, DMA_TO_DEVICE);
        __free_pages(page, WEIGHTS_ORDER);
        ret = -ERANGE;
        goto out_unlock;
    }

    if (!device_idle() || !safe_release() || readl(regs + REG_BASE)) {
        dma_unmap_single(fixture_dev, address, count, DMA_TO_DEVICE);
        __free_pages(page, WEIGHTS_ORDER);
        ret = -EBUSY;
        goto out_unlock;
    }

    /* The mapping synchronized the initialized bytes for device access.
     * Only explicit, verified CLEAR can undo this module reference.
     */
    __module_get(THIS_MODULE);
    weights = page;
    weights_dma = address;
    writel(lower_32_bits(weights_dma), regs + REG_BASE);
    ret = readl(regs + REG_BASE) == weights_dma ? count : -EIO;

out_unlock:
    mutex_unlock(&fixture_lock);
    kfree(image);
    return ret;
}

static int select_bram(void)
{
    if (!device_idle())
        return -EBUSY;
    if (safe_release())
        return 0;
    writel(0, regs + REG_CONTROL);
    return safe_release() ? 0 : -EBUSY;
}

static int select_ddr(void)
{
    u32 status;
    int ret;

    if (!weights)
        return -ENODATA;

    status = readl(regs + REG_CONTROL);
    if (status & KV260_DDR4_FAULT)
        return -EIO;
    if (!device_idle())
        return -EBUSY;
    if (readl(regs + REG_BASE) != weights_dma)
        return -EIO;

    if (translated) {
        ret = check_dma_domain(fixture_dev);
        if (ret)
            return ret;
    }
    if (status & KV260_DDR4_ENABLED)
        return 0;
    if (!(status & KV260_DDR4_SAFE_RELEASE))
        return -EBUSY;

    writel(1, regs + REG_CONTROL);
    status = readl(regs + REG_CONTROL);
    return (status & (KV260_DDR4_ENABLED | KV260_DDR4_FAULT)) ==
           KV260_DDR4_ENABLED ? 0 : -EIO;
}

static int clear_weights(void)
{
    int ret = select_bram();

    if (ret)
        return ret;

    if (!device_idle())
        return -EBUSY;
    if (readl(regs + REG_BASE))
        writel(0, regs + REG_BASE);
    if (readl(regs + REG_BASE) || !safe_release())
        return -EIO;

    if (weights) {
        dma_unmap_single(fixture_dev, weights_dma, KV260_DDR4_BYTES,
                       DMA_TO_DEVICE);
        __free_pages(weights, WEIGHTS_ORDER);
        weights = NULL;
        weights_dma = 0;
        module_put(THIS_MODULE);
    }
    return 0;
}

static long weights_ioctl(struct file *file, unsigned int command,
                          unsigned long argument)
{
    struct kv260_ddr4_state state;
    long ret;

    mutex_lock(&fixture_lock);
    if (!fixture_dev || !correct_fixture()) {
        ret = -ENODEV;
        goto out;
    }

    switch (command) {
    case KV260_DDR4_STATE:
        state.dma_base = lower_32_bits(weights_dma);
        state.dma_bytes = weights ? KV260_DDR4_BYTES : 0;
        state.hardware_base = readl(regs + REG_BASE);
        state.status = readl(regs + REG_CONTROL);
        state.useful_bytes = readl(regs + REG_USEFUL_BYTES);
        state.reads = readl(regs + REG_READS);
        state.beats = readl(regs + REG_BEATS);
        state.faults = readl(regs + REG_FAULTS);
        state.extra_clocks = readl(regs + REG_EXTRA_CLOCKS);
        state.ar_stalls = readl(regs + REG_AR_STALLS);
        state.response_wait = readl(regs + REG_RESPONSE_WAIT);
        state.projection_count = readl(regs + REG_PROJECTION_COUNT);
        state.projection_clocks = readl(regs + REG_PROJECTION_CLOCKS);
        state.magic = readl(regs + REG_FIXTURE);
        ret = copy_to_user((void __user *)argument, &state, sizeof(state)) ?
              -EFAULT : 0;
        break;
    case KV260_DDR4_BRAM:
        ret = select_bram();
        break;
    case KV260_DDR4_DDR:
        ret = select_ddr();
        break;
    case KV260_DDR4_CLEAR:
        ret = clear_weights();
        break;
    default:
        ret = -ENOTTY;
    }

out:
    mutex_unlock(&fixture_lock);
    return ret;
}

static const struct file_operations weights_fops = {
    .owner = THIS_MODULE,
    .open = weights_open,
    .release = weights_close,
    .write = weights_write,
    .unlocked_ioctl = weights_ioctl,
    .compat_ioctl = compat_ptr_ioctl,
    .llseek = no_llseek,
};

static struct miscdevice weights_misc = {
    .minor = MISC_DYNAMIC_MINOR,
    .name = "kv260-ddr4-weights",
    .fops = &weights_fops,
    .mode = 0600,
};

static int weights_probe(struct platform_device *pdev)
{
    struct device *dev = &pdev->dev;
    struct resource *resource;
    void __iomem *window, *status;
    bool uses_iommu;
    int ret;

    ret = check_dma_path(dev, &uses_iommu);
    if (ret)
        return dev_err_probe(dev, ret, "unverified HP0 DMA path\n");
    /*
     * Linux direct DMA requires a mask that covers its low allocator zone.
     * The direct API mask is 32 bits, the base register width. The FPGA's
     * smaller, routed aperture is checked before mapping and before MMIO.
     */
    ret = dma_set_mask(dev, DMA_BIT_MASK(uses_iommu ? 31 : 32));
    if (ret)
        return dev_err_probe(dev, ret, "HP0 streaming DMA mask unavailable\n");

    resource = platform_get_resource(pdev, IORESOURCE_MEM, 0);
    if (!resource || resource->start != MMIO_BASE ||
        resource_size(resource) != REG_FIXTURE + sizeof(u32))
        return -EINVAL;

    window = devm_ioremap_resource(dev, resource);
    if (IS_ERR(window))
        return PTR_ERR(window);

    /* Read-only status access in the existing UIO window. */
    status = devm_ioremap(dev, MODEL_STATUS, sizeof(u32));
    if (!status)
        return -ENOMEM;

    mutex_lock(&fixture_lock);
    if (fixture_dev || opened || weights) {
        ret = -EBUSY;
        goto out;
    }

    regs = window;
    model_status = status;
    if (!correct_fixture() || !device_idle() || !safe_release() ||
        readl(regs + REG_BASE)) {
        ret = -ENODEV;
        goto out;
    }

    fixture_dev = dev;
    translated = uses_iommu;
    weights_misc.parent = dev;
    ret = misc_register(&weights_misc);
    if (ret)
        fixture_dev = NULL;
    else
        dev_info(dev, "%s HP0 DMA admitted in low 2 GiB window\n",
                 translated ? "SMMU-translated" : "direct");
out:
    mutex_unlock(&fixture_lock);
    return ret;
}

static void weights_remove(struct platform_device *pdev)
{
    /* Deregister outside fixture_lock: misc_open holds its own mutex. */
    misc_deregister(&weights_misc);
    mutex_lock(&fixture_lock);
    if (weights)
        dev_crit(&pdev->dev,
                 "removed before verified CLEAR; DMA buffer pinned until reboot\n");
    fixture_dev = NULL;
    regs = NULL;
    model_status = NULL;
    mutex_unlock(&fixture_lock);
}

static const struct of_device_id weights_match[] = {
    { .compatible = "gradiated,kv260-ddr4-logits-v1" },
    {}
};
MODULE_DEVICE_TABLE(of, weights_match);

static struct platform_driver weights_driver = {
    .probe = weights_probe,
    .remove_new = weights_remove,
    .driver = {
        .name = "kv260-ddr4-weights",
        .of_match_table = weights_match,
        .suppress_bind_attrs = true,
    },
};
module_platform_driver(weights_driver);

MODULE_DESCRIPTION("KV260 DDR4 logits fixture weight ownership");
MODULE_LICENSE("GPL");
