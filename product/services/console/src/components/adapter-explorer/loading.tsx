export const ExplorerLoading = ({ message }: { message: string }) => (
  <div className="grid h-full place-items-center bg-[#030508] text-white">
    <div className="flex flex-col items-center gap-4">
      <span className="size-8 animate-spin rounded-full border-2 border-white/10 border-t-white/60" />
      <p className="text-sm text-white/60">{message}</p>
    </div>
  </div>
);
