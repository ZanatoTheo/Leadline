"use client";

import { useState, useCallback, useMemo } from "react";
import {
  ReactFlow,
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  NodeProps,
  Handle,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Network,
  Info,
  Eye,
  Users,
  TrendingUp,
  Link as LinkIcon,
} from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { INVESTORS, SYNDICATE_RELATIONSHIPS } from "@/lib/data/seed";
import { DEMO_COMPANY } from "@/lib/data/seed";
import { scoreAllInvestors } from "@/lib/scoring/leadScore";
import { formatCurrency } from "@/lib/utils";

const scoredMap = Object.fromEntries(
  scoreAllInvestors(DEMO_COMPANY).map(({ investor, score }) => [investor.id, score])
);

// ─── Custom Node ─────────────────────────────────────────────

function InvestorNode({ data }: NodeProps) {
  const score = scoredMap[data.id as string];
  const scoreVal = score?.totalScore ?? 0;
  const color =
    scoreVal >= 80 ? "#34d399" : scoreVal >= 60 ? "#818cf8" : scoreVal >= 40 ? "#fbbf24" : "#fb7185";
  const isConflict = score?.conflictStatus === "blocking";

  return (
    <div
      className={`px-4 py-3 rounded-xl border-2 shadow-lg min-w-[140px] cursor-pointer transition-all hover:scale-105 ${
        isConflict
          ? "border-rose-500/60 bg-rose-500/10"
          : "border-border bg-card"
      } ${data.isSelected ? "ring-2 ring-primary" : ""}`}
      style={{ borderColor: data.isSelected ? "hsl(239 84% 67%)" : isConflict ? "rgb(239 68 68 / 0.5)" : `${color}40` }}
    >
      <Handle type="target" position={Position.Left} className="opacity-0 w-2 h-2" />
      <div className="flex items-center gap-2 mb-2">
        <div
          className="h-7 w-7 rounded-lg flex items-center justify-center text-xs font-bold shrink-0"
          style={{ background: `${color}25`, border: `1px solid ${color}40` }}
        >
          {(data.label as string)?.[0]}
        </div>
        <div className="min-w-0">
          <div className="text-xs font-semibold truncate max-w-[90px]">{data.label as string}</div>
          <div className="text-[10px] text-muted-foreground truncate">{data.firm as string}</div>
        </div>
      </div>
      <div className="flex items-center justify-between">
        <div
          className="text-xs font-bold"
          style={{ color }}
        >
          {scoreVal}
        </div>
        {isConflict ? (
          <span className="text-[9px] text-rose-400 font-medium">CONFLICT</span>
        ) : (
          <span
            className="text-[9px] font-medium"
            style={{ color: `${color}cc` }}
          >
            {scoreVal >= 70 ? "LEAD" : "FOLLOW"}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="opacity-0 w-2 h-2" />
    </div>
  );
}

const nodeTypes = { investor: InvestorNode };

// ─── Build graph data ─────────────────────────────────────────

function buildGraph(selectedId: string | null) {
  const positions: Record<string, { x: number; y: number }> = {
    "accel-partners": { x: 350, y: 100 },
    "general-catalyst": { x: 700, y: 50 },
    "bessemer": { x: 650, y: 300 },
    "index-ventures": { x: 350, y: 300 },
    "sequoia": { x: 100, y: 180 },
    "craft-ventures": { x: 650, y: 500 },
    "felicis": { x: 900, y: 250 },
    "first-round": { x: 100, y: 400 },
    "khosla": { x: 50, y: 20 },
    "battery-ventures": { x: 900, y: 450 },
    "nea": { x: 450, y: 500 },
  };

  const nodes: Node[] = INVESTORS.map((inv) => ({
    id: inv.id,
    type: "investor",
    position: positions[inv.id] ?? { x: Math.random() * 800, y: Math.random() * 500 },
    data: {
      id: inv.id,
      label: inv.name,
      firm: inv.firm,
      isSelected: selectedId === inv.id,
    },
  }));

  const edges: Edge[] = SYNDICATE_RELATIONSHIPS.map((rel) => {
    const strength = rel.strength === "strong" ? 3 : rel.strength === "moderate" ? 2 : 1;
    return {
      id: `${rel.sourceId}-${rel.targetId}`,
      source: rel.sourceId,
      target: rel.targetId,
      style: {
        stroke:
          rel.strength === "strong"
            ? "rgba(99, 102, 241, 0.65)"
            : rel.strength === "moderate"
            ? "#94a3b8"
            : "#cbd5e1",
        strokeWidth: strength,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color:
          rel.strength === "strong"
            ? "rgba(99, 102, 241, 0.65)"
            : "#94a3b8",
      },
      label: `${rel.coInvestments}×`,
      labelStyle: { fill: "hsl(var(--muted-foreground))", fontSize: 10, fontFamily: "inherit" },
      labelBgStyle: { fill: "hsl(var(--card))", fillOpacity: 0.9 },
    };
  });

  return { nodes, edges };
}

export default function SyndicatePage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => buildGraph(selectedId),
    [selectedId]
  );

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  const selectedInvestor = selectedId ? INVESTORS.find((inv) => inv.id === selectedId) : null;
  const selectedScore = selectedId ? scoredMap[selectedId] : null;

  const relatedRels = selectedId
    ? SYNDICATE_RELATIONSHIPS.filter(
        (r) => r.sourceId === selectedId || r.targetId === selectedId
      )
    : [];

  const potentialSyndicate = relatedRels.map((r) => {
    const partnerId = r.sourceId === selectedId ? r.targetId : r.sourceId;
    return INVESTORS.find((inv) => inv.id === partnerId);
  }).filter(Boolean);

  return (
    <AppLayout>
      <div className="mb-5">
        <h1 className="text-2xl font-bold mb-1">Co-investment Networks</h1>
        <p className="text-muted-foreground text-sm">
          See which investors co-invest together and predict likely round compositions.
          Click any node to explore their relationships.
        </p>
      </div>

      <div className="mb-3 flex items-center gap-2 text-xs text-muted-foreground">
        <Info className="h-3.5 w-3.5" />
        All co-investment data is synthetic demonstration data.
        Arrow thickness indicates relationship strength (number of co-investments).
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 mb-4 text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <div className="h-0.5 w-6 bg-primary/60 rounded" />
          <span>Strong relationship (3+ co-investments)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="h-px w-6 bg-muted-foreground/40 rounded" />
          <span>Moderate relationship</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-3 w-3 rounded border border-rose-500/60 bg-rose-500/10" />
          <span>Portfolio conflict</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-3 w-3 rounded border border-emerald-500/40 bg-emerald-500/10" />
          <span>High-match investor</span>
        </div>
      </div>

      <div className="grid lg:grid-cols-4 gap-5 h-[calc(100vh-280px)] min-h-[500px]">
        {/* Graph */}
        <div className="lg:col-span-3 rounded-xl border border-border overflow-hidden">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            onNodeClick={(_, node) =>
              setSelectedId((prev) => (prev === node.id ? null : node.id))
            }
            fitView
            fitViewOptions={{ padding: 0.1 }}
            defaultEdgeOptions={{ animated: false }}
          >
            <Background color="hsl(var(--border))" gap={20} size={1} />
            <Controls className="border border-border" />
            <MiniMap
              nodeColor={(node) => {
                const score = scoredMap[node.id]?.totalScore ?? 0;
                return score >= 80 ? "#34d399" : score >= 60 ? "#818cf8" : "#475569";
              }}
              maskColor="hsl(var(--background) / 0.75)"
            />
          </ReactFlow>
        </div>

        {/* Detail panel */}
        <div className="space-y-4 overflow-y-auto">
          {selectedInvestor && selectedScore ? (
            <>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">{selectedInvestor.name}</CardTitle>
                  <p className="text-xs text-muted-foreground">{selectedInvestor.firm}</p>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Lead score</span>
                    <span
                      className={`font-bold ${
                        selectedScore.totalScore >= 80
                          ? "text-emerald-400"
                          : selectedScore.totalScore >= 60
                          ? "text-indigo-400"
                          : "text-amber-400"
                      }`}
                    >
                      {selectedScore.totalScore}
                    </span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Lead rate</span>
                    <span className="font-medium">
                      {Math.round(selectedInvestor.dna.leadRate * 100)}%
                    </span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Conflict</span>
                    <span
                      className={`font-medium capitalize ${
                        selectedScore.conflictStatus === "blocking"
                          ? "text-rose-400"
                          : selectedScore.conflictStatus === "none"
                          ? "text-emerald-400"
                          : "text-amber-400"
                      }`}
                    >
                      {selectedScore.conflictStatus}
                    </span>
                  </div>
                </CardContent>
              </Card>

              {potentialSyndicate.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Users className="h-3.5 w-3.5 text-indigo-400" />
                      Likely syndicate partners
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    {potentialSyndicate.map((partner) => {
                      if (!partner) return null;
                      const pScore = scoredMap[partner.id];
                      const rel = relatedRels.find(
                        (r) => r.sourceId === partner.id || r.targetId === partner.id
                      );
                      return (
                        <div
                          key={partner.id}
                          className="px-4 py-3 border-t border-border first:border-0 flex items-center gap-2"
                        >
                          <div className="h-6 w-6 rounded bg-secondary flex items-center justify-center text-[10px] font-bold shrink-0">
                            {partner.name[0]}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-xs font-medium truncate">{partner.name}</div>
                            <div className="text-[10px] text-muted-foreground">
                              {partner.firm} · {rel?.coInvestments}× co-invests
                            </div>
                          </div>
                          {pScore && (
                            <span
                              className={`text-xs font-bold shrink-0 ${
                                pScore.totalScore >= 70 ? "text-emerald-400" : "text-muted-foreground"
                              }`}
                            >
                              {pScore.totalScore}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </CardContent>
                </Card>
              )}

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Syndicate insight</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    If {selectedInvestor.name} leads your round, the syndicate data
                    suggests{" "}
                    {potentialSyndicate
                      .slice(0, 2)
                      .map((p) => p?.firm)
                      .join(" and ")}{" "}
                    may follow. This pattern has occurred in {relatedRels.reduce(
                      (sum, r) => sum + r.coInvestments,
                      0
                    )}{" "}
                    historical co-investments. <em>Synthetic data — not verified.</em>
                  </p>
                </CardContent>
              </Card>
            </>
          ) : (
            <Card>
              <CardContent className="pt-6 text-center">
                <Network className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">
                  Click an investor node to explore their syndicate relationships and
                  potential round composition.
                </p>
              </CardContent>
            </Card>
          )}

          {/* Stats */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Network overview</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {[
                { label: "Total investors", value: INVESTORS.length },
                { label: "Relationships mapped", value: SYNDICATE_RELATIONSHIPS.length },
                { label: "Strong ties", value: SYNDICATE_RELATIONSHIPS.filter((r) => r.strength === "strong").length },
              ].map((stat) => (
                <div key={stat.label} className="flex justify-between text-xs">
                  <span className="text-muted-foreground">{stat.label}</span>
                  <span className="font-medium">{stat.value}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppLayout>
  );
}
