import type { FileDiff } from "@/lib/api";

const STATUS_LABEL: Record<FileDiff["status"], { text: string; cls: string }> = {
  modified: { text: "修改", cls: "text-accent border-accent/40" },
  new: { text: "新增", cls: "text-ok border-ok/40" },
  deleted: { text: "删除", cls: "text-err border-err/40" },
};

/** Plan Diff Viewer（UI-02）：文件级 diff，等宽、红绿行。 */
export function DiffView({ diffs }: { diffs: FileDiff[] }) {
  if (diffs.length === 0) {
    return <p className="text-sm text-faint">无文件改动。</p>;
  }
  return (
    <div className="space-y-4">
      {diffs.map((d) => (
        <section key={d.path} className="overflow-hidden rounded-md border border-edge">
          <header className="flex items-center gap-3 border-b border-edge bg-panel-2 px-3 py-2">
            <span className={`rounded-sm border px-1.5 font-mono text-[10px] ${STATUS_LABEL[d.status].cls}`}>
              {STATUS_LABEL[d.status].text}
            </span>
            <span className="font-mono text-xs text-ink">{d.path}</span>
          </header>
          <pre className="data-scroll max-h-80 overflow-auto bg-bg p-0 font-mono text-xs leading-5">
            {renderLines(d).map((l, i) => (
              <div
                key={i}
                className={
                  l.type === "add"
                    ? "bg-ok/10 px-3 text-ok"
                    : l.type === "remove"
                      ? "bg-err/10 px-3 text-err line-through/0"
                      : "px-3 text-muted"
                }
              >
                <span className="mr-2 select-none text-faint">
                  {l.type === "add" ? "+" : l.type === "remove" ? "−" : " "}
                </span>
                {l.line || " "}
              </div>
            ))}
          </pre>
        </section>
      ))}
    </div>
  );
}

function renderLines(d: FileDiff): { type: "add" | "remove" | "ctx"; line: string }[] {
  if (d.status === "modified" && d.diff) {
    return d.diff.map((c) => ({ type: c.type, line: c.line.replace(/\n$/, "") }));
  }
  if (d.status === "new" && d.current) {
    return d.current.split("\n").map((line) => ({ type: "add" as const, line }));
  }
  if (d.status === "deleted" && d.original) {
    return d.original.split("\n").map((line) => ({ type: "remove" as const, line }));
  }
  return [];
}
