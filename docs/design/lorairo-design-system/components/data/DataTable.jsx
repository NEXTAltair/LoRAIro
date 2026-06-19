import React from "react";

/**
 * DataTable — the LoRAIro list/table style (paper-shade header, hairline rows,
 * hover + selected tint). `columns` = [{ key, header, width, align, render }].
 * `rows` = array of row objects. `rowKey` picks a stable key; `selectedKey`
 * tints a row; `onRowClick(row)` is optional.
 */
export function DataTable({
  columns = [],
  rows = [],
  rowKey = (r, i) => r.id ?? i,
  selectedKey,
  onRowClick,
  style,
}) {
  const [hover, setHover] = React.useState(null);
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "var(--fs-base)", ...style }}>
      <thead>
        <tr>
          {columns.map((c) => (
            <th
              key={c.key}
              style={{
                fontSize: "var(--fs-small)",
                fontWeight: 600,
                color: "var(--ink-soft)",
                textAlign: c.align || "left",
                padding: "6px 10px",
                borderBottom: "1px solid var(--line-strong)",
                background: "var(--paper-shade)",
                width: c.width,
                whiteSpace: "nowrap",
              }}
            >
              {c.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => {
          const key = rowKey(row, i);
          const selected = selectedKey != null && key === selectedKey;
          const isHover = hover === key;
          return (
            <tr
              key={key}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onMouseEnter={() => setHover(key)}
              onMouseLeave={() => setHover(null)}
              style={{ cursor: onRowClick ? "pointer" : "default" }}
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  style={{
                    padding: "7px 10px",
                    borderBottom: "1px solid var(--line)",
                    textAlign: c.align || "left",
                    verticalAlign: "middle",
                    background: selected
                      ? "var(--accent-soft)"
                      : isHover
                      ? "var(--paper-shade)"
                      : "transparent",
                  }}
                >
                  {c.render ? c.render(row) : row[c.key]}
                </td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
