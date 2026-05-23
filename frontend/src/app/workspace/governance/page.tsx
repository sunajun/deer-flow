"use client";

import {
  BotIcon,
  KeyRoundIcon,
  PackageIcon,
} from "lucide-react";
import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const GOVERNANCE_CARDS = [
  {
    title: "Agent Management",
    description: "Manage agent configurations with version tracking and rollback",
    href: "/workspace/governance/agents",
    icon: BotIcon,
  },
  {
    title: "Skill Management",
    description: "Install, enable, disable, and update skills",
    href: "/workspace/governance/skills",
    icon: PackageIcon,
  },
  {
    title: "Permission Configuration",
    description: "Configure role-based access control and permissions",
    href: "/workspace/governance/permissions",
    icon: KeyRoundIcon,
  },
];

export default function GovernancePage() {
  return (
    <div className="flex size-full flex-col">
      <div className="border-b px-6 py-4">
        <h1 className="text-xl font-semibold">Governance</h1>
        <p className="text-muted-foreground mt-0.5 text-sm">
          Unified governance dashboard for agents, skills, and permissions
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {GOVERNANCE_CARDS.map((card) => (
            <Link key={card.href} href={card.href}>
              <Card className="transition-colors hover:bg-muted/50">
                <CardHeader>
                  <div className="flex items-center gap-3">
                    <div className="bg-muted flex h-10 w-10 items-center justify-center rounded-lg">
                      <card.icon className="text-muted-foreground h-5 w-5" />
                    </div>
                    <CardTitle className="text-base">{card.title}</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-muted-foreground text-sm">
                    {card.description}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
