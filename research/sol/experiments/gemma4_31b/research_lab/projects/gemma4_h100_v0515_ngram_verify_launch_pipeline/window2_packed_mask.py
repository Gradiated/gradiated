import torch


def pack_full_mask(mask, seq_lens_cpu, draft_token_num, device):
    rows = []
    for i, seq_len in enumerate(seq_lens_cpu):
        rows.append(torch.cat((torch.ones((draft_token_num, int(seq_len)), dtype=torch.bool), torch.from_numpy(mask[i]).to(torch.bool)), dim=1).reshape(-1))
    host = torch.cat(rows).pin_memory()
    return host.to(device=device, non_blocking=True)
