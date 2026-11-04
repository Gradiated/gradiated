import type { Meta, StoryObj } from "@storybook/react-vite";

import { Canvas } from "@/stories/states";
import { Badge } from "./badge";
import { Skeleton } from "./skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "./table";

const rows = [
  {
    name: "Production",
    prefix: "gr_live_3f9a",
    created: "Oct 2, 2026",
    status: "Active",
  },
  {
    name: "CI",
    prefix: "gr_live_81bc",
    created: "Sep 14, 2026",
    status: "Active",
  },
  {
    name: "Old laptop",
    prefix: "gr_live_0d42",
    created: "Mar 3, 2026",
    status: "Revoked",
  },
];

const meta = { title: "Components/Table" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const Header = () => (
  <TableHeader>
    <TableRow>
      <TableHead>Name</TableHead>
      <TableHead>Key</TableHead>
      <TableHead>Created</TableHead>
      <TableHead className="text-right">Status</TableHead>
    </TableRow>
  </TableHeader>
);

export const Populated: Story = {
  render: () => (
    <Canvas>
      <Table>
        <TableCaption>API keys for the Production workspace.</TableCaption>
        <Header />
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.prefix}>
              <TableCell className="font-medium">{row.name}</TableCell>
              <TableCell className="font-mono text-xs">{row.prefix}…</TableCell>
              <TableCell>{row.created}</TableCell>
              <TableCell className="text-right">
                <Badge
                  variant={row.status === "Active" ? "secondary" : "outline"}
                >
                  {row.status}
                </Badge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell colSpan={3}>Total</TableCell>
            <TableCell className="text-right">3 keys</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    </Canvas>
  ),
};

export const Selected: Story = {
  render: () => (
    <Canvas>
      <Table>
        <Header />
        <TableBody>
          {rows.map((row, index) => (
            <TableRow
              key={row.prefix}
              data-state={index === 1 ? "selected" : undefined}
            >
              <TableCell className="font-medium">{row.name}</TableCell>
              <TableCell className="font-mono text-xs">{row.prefix}…</TableCell>
              <TableCell>{row.created}</TableCell>
              <TableCell className="text-right">{row.status}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Canvas>
  ),
};

export const Loading: Story = {
  render: () => (
    <Canvas>
      <Table>
        <Header />
        <TableBody>
          {[0, 1, 2].map((row) => (
            <TableRow key={row}>
              {[0, 1, 2, 3].map((cell) => (
                <TableCell key={cell}>
                  <Skeleton className="h-4 w-24" />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Canvas>
  ),
};

export const Empty: Story = {
  render: () => (
    <Canvas>
      <Table>
        <Header />
        <TableBody>
          <TableRow>
            <TableCell
              colSpan={4}
              className="h-24 text-center text-muted-foreground"
            >
              No API keys yet.
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </Canvas>
  ),
};
