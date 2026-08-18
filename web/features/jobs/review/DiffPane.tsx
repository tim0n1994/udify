import { diffLines } from "diff";
import { FileCode2 } from "lucide-react";
import { EmptyState } from "@/components/ui/States";
import type { FileDiff, SourceSpan } from "@/lib/api";
import { cn } from "@/lib/cn";

interface DiffLine {
  kind: "add" | "remove" | "context";
  text: string;
  oldLine: number | null;
  newLine: number | null;
}

export function buildDiffLines(diff: FileDiff): DiffLine[] {
  let oldLine = 1;
  let newLine = 1;
  const lines: DiffLine[] = [];
  for (const part of diffLines(diff.original ?? "", diff.current ?? "")) {
    const values = part.value.endsWith("\n")
      ? part.value.slice(0, -1).split("\n")
      : part.value.split("\n");
    for (const text of values) {
      if (part.added) {
        lines.push({ kind: "add", text, oldLine: null, newLine: newLine++ });
      } else if (part.removed) {
        lines.push({ kind: "remove", text, oldLine: oldLine++, newLine: null });
      } else {
        lines.push({ kind: "context", text, oldLine: oldLine++, newLine: newLine++ });
      }
    }
  }
  return lines;
}

export function DiffPane({ diff, anchor }: { diff: FileDiff | null; anchor?: SourceSpan }) {
  if (!diff) return <EmptyState title="没有文件 diff" description="该计划未产生文件级修改。" />;
  const lines = buildDiffLines(diff);
  const anchorMatches = anchor?.file_path === diff.path;
  return (
    <section className="min-w-0 bg-bg/40" aria-label={`${diff.path} diff`}>
      <header className="flex items-center gap-2 border-b border-edge bg-panel-2 px-3 py-2.5">
        <FileCode2 className="h-4 w-4 text-accent" aria-hidden />
        <h2 className="min-w-0 truncate font-mono text-xs text-ink">{diff.path}</h2>
        <span className="ml-auto border border-edge px-2 py-0.5 font-mono text-[9px] uppercase text-muted">{diff.status}</span>
      </header>
      {lines.length > 0 ? (
        <div className="data-scroll max-h-[420px] overflow-auto font-mono text-[11px] leading-5">
          <table className="w-full min-w-[620px] border-collapse">
            <tbody>
              {lines.map((line, index) => {
                const referenceLine = line.newLine ?? line.oldLine;
                const highlighted = Boolean(
                  anchorMatches &&
                    referenceLine &&
                    anchor?.line_start != null &&
                    referenceLine >= anchor.line_start &&
                    referenceLine <= (anchor.line_end ?? anchor.line_start),
                );
                return (
                  <tr
                    key={`${line.kind}-${line.oldLine}-${line.newLine}-${index}`}
                    data-highlighted={highlighted || undefined}
                    className={cn(
                      line.kind === "add" && "bg-ok/12 text-ok",
                      line.kind === "remove" && "bg-err/12 text-err",
                      line.kind === "context" && "text-muted",
                      highlighted && "ring-1 ring-inset ring-accent bg-accent/12",
                    )}
                  >
                    <td className="w-10 select-none border-r border-edge/60 px-2 text-right text-faint">{line.oldLine ?? ""}</td>
                    <td className="w-10 select-none border-r border-edge/60 px-2 text-right text-faint">{line.newLine ?? ""}</td>
                    <td className="w-6 select-none px-2 text-center">{line.kind === "add" ? "+" : line.kind === "remove" ? "−" : " "}</td>
                    <td className="whitespace-pre px-2">{line.text || " "}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="空 diff" description="后端报告了文件变更，但内容前后相同。" />
      )}
      <footer className="border-t border-edge px-3 py-2 font-mono text-[10px] text-faint">
        {anchorMatches
          ? anchor?.line_start != null
            ? `已定位 SourceSpan ${anchor.line_start}-${anchor.line_end ?? anchor.line_start}`
            : "已定位证据文件；后端 SourceSpan 未提供行号，无法高亮到行"
          : "选择下方操作可定位 SourceSpan 证据"}
      </footer>
    </section>
  );
}
