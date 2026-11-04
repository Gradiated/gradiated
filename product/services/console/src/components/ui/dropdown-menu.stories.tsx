import type { Meta, StoryObj } from "@storybook/react-vite";
import { LogOut, Settings, Trash2, User } from "lucide-react";
import { useState } from "react";
import { userEvent, within } from "storybook/test";

import { Canvas } from "@/stories/states";
import { Button } from "./button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "./dropdown-menu";

const meta = { title: "Components/Dropdown menu" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const openMenu: Story["play"] = async ({ canvasElement }) => {
  await userEvent.click(
    within(canvasElement).getByRole("button", { name: "Open menu" }),
  );
  await within(document.body).findByRole("menu");
};

export const Closed: Story = {
  render: () => (
    <Canvas>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline">Open menu</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem>Profile</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </Canvas>
  ),
};

export const Items: Story = {
  render: () => (
    <Canvas>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline">Open menu</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent className="w-56" align="start">
          <DropdownMenuLabel>alex@example.com</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuItem>
              <User />
              Profile
              <DropdownMenuShortcut>⇧⌘P</DropdownMenuShortcut>
            </DropdownMenuItem>
            <DropdownMenuItem>
              <Settings />
              Settings
              <DropdownMenuShortcut>⌘,</DropdownMenuShortcut>
            </DropdownMenuItem>
            <DropdownMenuItem disabled>Billing (disabled)</DropdownMenuItem>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem className="text-destructive focus:text-destructive">
            <Trash2 />
            Delete workspace
          </DropdownMenuItem>
          <DropdownMenuItem>
            <LogOut />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </Canvas>
  ),
  play: openMenu,
};

const CheckboxMenu = () => {
  const [columns, setColumns] = useState({
    Model: true,
    Cost: true,
    Latency: false,
  });

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline">Open menu</Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-48" align="start">
        <DropdownMenuLabel>Columns</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {(Object.keys(columns) as (keyof typeof columns)[]).map((column) => (
          <DropdownMenuCheckboxItem
            key={column}
            checked={columns[column]}
            onCheckedChange={(checked) =>
              setColumns((current) => ({ ...current, [column]: checked }))
            }
          >
            {column}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export const CheckboxItems: Story = {
  render: () => (
    <Canvas>
      <CheckboxMenu />
    </Canvas>
  ),
  play: openMenu,
};

const RadioMenu = () => {
  const [range, setRange] = useState("7d");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline">Open menu</Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-48" align="start">
        <DropdownMenuLabel>Time range</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup value={range} onValueChange={setRange}>
          <DropdownMenuRadioItem value="24h">
            Last 24 hours
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="7d">Last 7 days</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="30d">
            Last 30 days
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export const RadioItems: Story = {
  render: () => (
    <Canvas>
      <RadioMenu />
    </Canvas>
  ),
  play: openMenu,
};

export const Submenu: Story = {
  render: () => (
    <Canvas>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline">Open menu</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent className="w-48" align="start">
          <DropdownMenuItem>New workspace</DropdownMenuItem>
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>Switch workspace</DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              <DropdownMenuItem>Production</DropdownMenuItem>
              <DropdownMenuItem>Staging</DropdownMenuItem>
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        </DropdownMenuContent>
      </DropdownMenu>
    </Canvas>
  ),
  play: async (context) => {
    await openMenu(context);
    await userEvent.click(
      await within(document.body).findByRole("menuitem", {
        name: "Switch workspace",
      }),
    );
    await within(document.body).findByRole("menuitem", { name: "Staging" });
  },
};
