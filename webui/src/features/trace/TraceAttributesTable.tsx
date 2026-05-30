type TraceAttributesTableProps = {
  rows: Array<[string, string]>;
};

function formatCellValue(value: string): string {
  return value;
}

function valueKind(value: string): "string" | "number" | "bool" | "json" {
  if (value === "true" || value === "false") return "bool";
  if (/^-?\d+(\.\d+)?$/.test(value)) return "number";
  if (value.startsWith("{") || value.startsWith("[")) return "json";
  return "string";
}

/** Jaeger ``KeyValueTable`` — bordered tag table for span detail sections. */
export function TraceAttributesTable(props: TraceAttributesTableProps) {
  const { rows } = props;
  if (!rows.length) {
    return <p className="trace-kv-table-empty">—</p>;
  }

  return (
    <div className="trace-kv-table-wrap">
      <table className="trace-kv-table">
        <tbody>
          {rows.map(([key, value], index) => (
            <tr key={`${key}-${index}`}>
              <td className="trace-kv-table-key">{key}</td>
              <td className={`trace-kv-table-value trace-kv-value-${valueKind(value)}`}>
                {formatCellValue(value)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
