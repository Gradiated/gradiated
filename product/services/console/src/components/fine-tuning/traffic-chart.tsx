import { useState } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { SegmentedControl } from "@/pages/segmented-control";

export const TrafficChart = () => {
  const [metric, setMetric] = useState<"cost" | "requests" | "tokens">("cost");
  const [days, setDays] = useState<30 | 90 | 180>(30);

  return (
    <section>
      <h2 className="mb-2 text-sm font-medium">Traffic</h2>
      <Card className="shadow-sm">
        <CardHeader className="flex-row items-center justify-between gap-4 border-b p-4">
          <SegmentedControl
            value={metric}
            onChange={setMetric}
            options={[
              { value: "cost", label: "Cost" },
              { value: "requests", label: "Requests" },
              { value: "tokens", label: "Tokens" },
            ]}
          />
          <SegmentedControl
            value={days}
            onChange={setDays}
            options={[
              { value: 30, label: "30d" },
              { value: 90, label: "90d" },
              { value: 180, label: "180d" },
            ]}
          />
        </CardHeader>
        <CardContent className="flex h-[280px] items-center justify-center p-5 text-sm text-muted-foreground">
          Traffic data is not available yet.
        </CardContent>
      </Card>
    </section>
  );
};
