/**
 * SprintReportChart — 扫榜数据可视化（Sprint 5 第 1 批）
 *
 * 复用 Recharts (已装)。
 * 输入: markdown 文本中提取的表格数据（{label, value}[]），
 * 输出: 4 类图表（条形 / 折线 / 饼 / 散点）。
 *
 * Markdown 表格格式:
 *   | 维度 | 热度 |
 *   | 玄幻 | 0.35 |
 *   | 都市 | 0.22 |
 */

import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

import { Stack, Typography, Box, Alert, ToggleButton, ToggleButtonGroup } from '@mui/material';
import BarChartIcon from '@mui/icons-material/BarChart';
import ShowChartIcon from '@mui/icons-material/ShowChart';
import PieChartIcon from '@mui/icons-material/PieChart';
import ScatterPlotIcon from '@mui/icons-material/ScatterPlot';

import { useState } from 'react';

export interface ChartPoint {
  label: string;
  value: number;
  /** 第二维度（散点用） */
  y?: number;
}

interface SprintReportChartProps {
  /** 从 markdown 表格提取的数据点 */
  data: ChartPoint[];
  /** 图表标题 */
  title?: string;
  /** 默认图表类型 */
  defaultType?: ChartType;
}

export type ChartType = 'bar' | 'line' | 'pie' | 'scatter';

const COLORS = [
  '#1976d2', '#388e3c', '#f57c00', '#d32f2f', '#7b1fa2',
  '#0288d1', '#fbc02d', '#5d4037', '#455a64', '#c2185b',
];

export function SprintReportChart({
  data,
  title,
  defaultType = 'bar',
}: SprintReportChartProps) {
  const [chartType, setChartType] = useState<ChartType>(defaultType);

  // 散点需要两个数：value 和 y。如果 y 缺失，自动生成序号
  const scatterData = useMemo(() => {
    return data.map((d, idx) => ({
      x: d.value,
      y: d.y ?? idx + 1,
      label: d.label,
    }));
  }, [data]);

  if (data.length === 0) {
    return (
      <Alert severity="info">
        暂无图表数据（markdown 中未检测到表格）
      </Alert>
    );
  }

  return (
    <Box>
      {title && (
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          {title}
        </Typography>
      )}
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <Typography variant="caption" color="text.secondary">
          图表类型：
        </Typography>
        <ToggleButtonGroup
          size="small"
          value={chartType}
          exclusive
          onChange={(_, v) => v && setChartType(v)}
        >
          <ToggleButton value="bar" data-testid="chart-type-bar">
            <BarChartIcon fontSize="small" />
          </ToggleButton>
          <ToggleButton value="line" data-testid="chart-type-line">
            <ShowChartIcon fontSize="small" />
          </ToggleButton>
          <ToggleButton value="pie" data-testid="chart-type-pie">
            <PieChartIcon fontSize="small" />
          </ToggleButton>
          <ToggleButton value="scatter" data-testid="chart-type-scatter">
            <ScatterPlotIcon fontSize="small" />
          </ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      <Box sx={{ width: '100%', height: 320 }}>
        <ResponsiveContainer>
          {chartType === 'bar' ? (
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" angle={-25} textAnchor="end" height={70} interval={0} fontSize={12} />
              <YAxis fontSize={12} />
              <Tooltip />
              <Bar dataKey="value" fill={COLORS[0]} />
            </BarChart>
          ) : chartType === 'line' ? (
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" angle={-25} textAnchor="end" height={70} interval={0} fontSize={12} />
              <YAxis fontSize={12} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="value" stroke={COLORS[0]} dot={{ r: 4 }} />
            </LineChart>
          ) : chartType === 'pie' ? (
            <PieChart>
              <Pie
                data={data}
                dataKey="value"
                nameKey="label"
                cx="50%"
                cy="50%"
                outerRadius={100}
                label={(entry) => `${entry.label}: ${entry.value}`}
              >
                {data.map((_, idx) => (
                  <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          ) : (
            <ScatterChart>
              <CartesianGrid />
              <XAxis type="number" dataKey="x" name="X" fontSize={12} />
              <YAxis type="number" dataKey="y" name="Y" fontSize={12} />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} />
              <Scatter data={scatterData} fill={COLORS[0]} />
            </ScatterChart>
          )}
        </ResponsiveContainer>
      </Box>
    </Box>
  );
}

/**
 * 从 markdown 文本中提取所有表格（按 ## 章节分组）。
 * 表格格式:
 *   | 列1 | 列2 |
 *   | --- | --- |
 *   | 玄幻 | 0.35 |
 *
 * 返回: [{ heading, columns, rows }]
 */
export interface MarkdownTable {
  heading: string;
  columns: string[];
  rows: Array<Record<string, string>>;
}

export function parseMarkdownTables(markdown: string): MarkdownTable[] {
  const lines = markdown.split('\n');
  const tables: MarkdownTable[] = [];

  let currentHeading = '';
  let i = 0;
  while (i < lines.length) {
    const line = lines[i] ?? '';
    // 检测 ## 标题
    const h = line.match(/^#{1,3}\s+(.+)/);
    if (h && h[1]) {
      currentHeading = h[1].trim();
      i++;
      continue;
    }

    // 检测表格（以 | 开头的行 + 下一行是分隔行）
    const nextLine = lines[i + 1] ?? '';
    if (line.trim().startsWith('|') && /^\|[\s\-:|]+\|/.test(nextLine)) {
      const columns = line
        .split('|')
        .map((c) => c.trim())
        .filter((c) => c);
      const rows: Array<Record<string, string>> = [];
      i += 2;
      while (i < lines.length) {
        const curLine = lines[i] ?? '';
        if (!curLine.trim().startsWith('|')) break;
        const rowCells = curLine
          .split('|')
          .map((c) => c.trim())
          .filter((c) => c);
        const row: Record<string, string> = {};
        columns.forEach((col, idx) => {
          row[col] = rowCells[idx] ?? '';
        });
        rows.push(row);
        i++;
      }
      tables.push({ heading: currentHeading || '未分类', columns, rows });
      continue;
    }

    i++;
  }

  return tables;
}

/**
 * 把 markdown 表格 rows 转成 ChartPoint[]（取第一列 label + 第二个数值列 value）
 */
export function tableRowsToChartPoints(
  rows: Array<Record<string, string>>,
  valueColumn?: string,
): ChartPoint[] {
  if (rows.length === 0) return [];
  const firstRow = rows[0];
  if (!firstRow) return [];
  const keys = Object.keys(firstRow);
  const firstCol = keys[0];
  if (!firstCol) return [];
  const valCol =
    valueColumn ??
    keys.find((k) => k !== firstCol && /^[+-]?\d/.test(firstRow[k] ?? '')) ??
    keys[1];

  return rows
    .map((row) => {
      const label = row[firstCol] ?? '';
      const rawVal = valCol ? row[valCol] ?? '0' : '0';
      const num = parseFloat(rawVal.replace(/[^\d.\-eE+]/g, ''));
      return { label, value: isNaN(num) ? 0 : num };
    })
    .filter((p) => p.label && !isNaN(p.value));
}
