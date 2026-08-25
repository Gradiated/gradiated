import { WaitlistLink } from "./WaitlistDialog";
import type { ReactElement } from "react";

type ProductSectionProps = {
  onWaitlist: () => void;
};

export const ProductSection = ({
  onWaitlist,
}: ProductSectionProps): ReactElement => (
  <section
    className="product grid grid-cols-[minmax(0,1.35fr)_minmax(320px,.65fr)] gap-0 border-b border-line px-7 py-36 max-site:grid-cols-1 max-site:px-5 max-site:py-24"
    aria-labelledby="kimi-k3-title"
  >
    <div className="product-art min-h-[480px] overflow-hidden bg-ink max-site:aspect-[2/1] max-site:min-h-[260px]">
      <img
        className="block h-full w-full object-cover saturate-product transition-[transform,filter] duration-700 ease-editorial hover:scale-product-hover hover:saturate-product-hover"
        src="/assets/editorial/kimi-k3-v2.png"
        alt="A layered academy-like system of chambers, passages and researchers"
        width="1772"
        height="887"
        loading="lazy"
      />
    </div>
    <div className="product-copy flex flex-col border-b border-line border-t border-ink pb-6 pl-12 pt-8 max-site:min-h-96 max-site:border-t-0 max-site:pl-0 max-site:pt-8">
      <p>Private beta · Optimized inference</p>
      <h2 id="kimi-k3-title">Kimi K3.</h2>
      <span>
        The world&apos;s most efficient Kimi K3 inference, in private beta.
      </span>
      <WaitlistLink className="text-link mt-auto pt-12" onOpen={onWaitlist}>
        Request beta access <b>→</b>
      </WaitlistLink>
    </div>
  </section>
);
