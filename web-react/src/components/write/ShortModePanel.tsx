/**
 * ShortModePanel: 短篇 8 节 tab 视图 (Sprint 3 / V1.5.3)
 *
 * 短篇结构（story-short-write skill §1）：
 *   1. 起势（建立）
 *   2. 钩子（引发好奇）
 *   3. 转折（第一次反转）
 *   4. 升级（矛盾加深）
 *   5. 危机（最强张力）
 *   6. 反转（核心揭秘）
 *   7. 收束（情感落地）
 *   8. 余韵（留白 / 钩尾）
 *
 * 数据流:
 *   - 8 个 section state（每个：prompt + 内容 + 加载状态）
 *   - useExecuteSkill('story-short-write') + useSkillStream
 *   - 传 section_index (0-7) + emotion + plot_prompt + extra_params
 *   - 每节独立调 skill，SSE 流式生成
 */

import { useState } from 'react';
import {
  Box,
  Tabs,
  Tab,
  Card,
  CardContent,
  Stack,
  Typography,
  TextField,
  Button,
  CircularProgress,
  Alert,
  Chip,
  Divider,
} from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import SaveIcon from '@mui/icons-material/Save';

import { useExecuteSkill } from '../../api/skills';
import { useSkillStream } from '../../hooks/useSkillStream';
import { useSnackbar } from '../../hooks/useSnackbar';
import { newIdempotencyKey } from '../../utils/idem';

const SKILL_NAME = 'story-short-write';
const DEFAULT_PROJECT_ROOT = '.';

interface SectionDef {
  index: number;
  key: string;        // 短 key（英文）
  title: string;      // 中文标题
  hint: string;       // 输入提示
  emotion: string;    // 默认情绪类型
}

const SECTIONS: SectionDef[] = [
  { index: 0, key: 'setup',  title: '1. 起势',   hint: '主角身份/处境/世界观',         emotion: '建立' },
  { index: 1, key: 'hook',   title: '2. 钩子',   hint: '第一个冲突/悬念/反常事件',       emotion: '好奇' },
  { index: 2, key: 'turn1',  title: '3. 转折',   hint: '第一次反转：主角认知颠覆',      emotion: '惊讶' },
  { index: 3, key: 'rise',   title: '4. 升级',   hint: '矛盾加深：对手/时间/代价升级',  emotion: '紧张' },
  { index: 4, key: 'crisis', title: '5. 危机',   hint: '最低谷/最强张力/最大抉择',      emotion: '绝望' },
  { index: 5, key: 'turn2',  title: '6. 反转',   hint: '核心揭秘：前文铺垫的回收',      emotion: '震撼' },
  { index: 6, key: 'close',  title: '7. 收束',   hint: '情感落地/角色选择/代价结算',    emotion: '释然' },
  { index: 7, key: 'echo',  title: '8. 余韵',   hint: '钩尾/留白/回扣开头',             emotion: '回味' },
];

export interface ShortModePanelProps {
  /** 故事核（一句话讲清核心反转 / 情节） */
  storyCore: string;

  /** 平台风格（盐言/番茄/七猫/默认） */
  platform?: string;

  /** 目标字数（3000-8000） */
  targetChars?: number;

  /** 章节号（用于显示，当前未使用，保留供未来扩展） */
  chapter?: number;

  /** 保存整篇（emit 最终拼接的 markdown） */
  onSave: (fullMarkdown: string) => void;
}

export function ShortModePanel({
  storyCore,
  platform = '盐言',
  targetChars = 5000,
  onSave,
}: ShortModePanelProps) {
  const { show } = useSnackbar();
  const [activeTab, setActiveTab] = useState(0);
  const [sections, setSections] = useState<Record<number, { prompt: string; text: string; loading: boolean; taskId: string | null }>>({});
  const [genre, setGenre] = useState('虐文');

  const executeSkill = useExecuteSkill(SKILL_NAME);
  const { stream, cancel } = useSkillStream();

  const section = SECTIONS[activeTab] ?? null;
  const data = section
    ? (sections[section.index] ?? { prompt: '', text: '', loading: false, taskId: null })
    : { prompt: '', text: '', loading: false, taskId: null };

  const setSectionData = (index: number, patch: Partial<typeof data>) => {
    setSections((prev) => ({
      ...prev,
      [index]: { ...(prev[index] ?? { prompt: '', text: '', loading: false, taskId: null }), ...patch },
    }));
  };

  /** 调 skill 生成当前 section */
  const handleGenerate = async (index: number) => {
    const sd = sections[index] ?? { prompt: '', text: '', loading: false, taskId: null };
    if (!sd.prompt.trim() && !storyCore.trim()) {
      show('请输入本节 prompt 或填写故事核', 'warning');
      return;
    }

    setSectionData(index, { loading: true, text: '' });

    const key = newIdempotencyKey();
    try {
      const resp = await executeSkill.mutateAsync({
        params: {
          story_core: storyCore.trim(),
          section_index: index,
          section_key: SECTIONS[index]!.key,
          emotion: SECTIONS[index]!.emotion,
          genre,
          platform,
          target_chars: Math.round(targetChars / 8),  // 8 节均分
          extra_hint: sd.prompt.trim(),
        },
        projectRoot: DEFAULT_PROJECT_ROOT,
        idempotencyKey: key,
      });

      setSectionData(index, { taskId: resp.task_id });

      const chunks: string[] = [];
      await stream({
        taskId: resp.task_id,
        skillName: SKILL_NAME,
        onChunk: (text) => {
          chunks.push(text);
          setSectionData(index, { text: chunks.join('') });
        },
        onError: (err) => {
          show(err instanceof Error ? err.message : '生成失败', 'error');
          setSectionData(index, { loading: false });
        },
        onDone: (output) => {
          setSectionData(index, { text: output.text, loading: false, taskId: null });
          show(`第 ${index + 1} 节生成完成（${output.text.length} 字）`, 'success');
        },
      });
    } catch (err) {
      show(err instanceof Error ? err.message : '启动失败', 'error');
      setSectionData(index, { loading: false });
    }
  };

  /** 拼成完整 markdown */
  const buildFullMarkdown = (): string => {
    const header = `# 短篇\n\n**故事核**: ${storyCore}\n\n**平台**: ${platform}\n**题材**: ${genre}\n**目标字数**: ${targetChars}\n\n---\n\n`;
    const body = SECTIONS.map((s) => {
      const txt = sections[s.index]?.text ?? '';
      return `## ${s.title}\n\n${txt || '（未生成）'}\n`;
    }).join('\n');
    return header + body;
  };

  const completedCount = SECTIONS.filter((s) => (sections[s.index]?.text?.length ?? 0) > 0).length;
  const totalChars = SECTIONS.reduce((sum, s) => sum + (sections[s.index]?.text?.length ?? 0), 0);

  if (!section) {
    return <Alert severity="warning">无效的章节序号</Alert>;
  }

  return (
    <Card variant="outlined" sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ borderBottom: 1, borderColor: 'divider', p: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
        <Tabs
          value={activeTab}
          onChange={(_, v) => setActiveTab(v)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ minHeight: 36, flex: 1 }}
        >
          {SECTIONS.map((s, idx) => {
            const filled = (sections[s.index]?.text?.length ?? 0) > 0;
            return (
              <Tab
                key={s.key}
                value={idx}
                label={
                  <Stack direction="row" spacing={0.5} alignItems="center">
                    <span>{s.title}</span>
                    {filled && <Chip size="small" label="✓" color="success" sx={{ height: 18 }} />}
                  </Stack>
                }
              />
            );
          })}
        </Tabs>
      </Box>

      <CardContent sx={{ flex: 1, overflow: 'auto' }}>
        <Stack spacing={2}>
          {/* 元数据 */}
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip size="small" label={`故事核: ${storyCore.slice(0, 30)}${storyCore.length > 30 ? '...' : ''}`} variant="outlined" />
            <Chip size="small" label={`平台: ${platform}`} variant="outlined" />
            <Chip size="small" label={`${completedCount}/8 节完成`} color={completedCount === 8 ? 'success' : 'default'} />
            <Chip size="small" label={`总 ${totalChars} 字`} color="primary" />
          </Stack>

          {/* prompt 输入 */}
          <TextField
            label={`${section.title} 补充说明`}
            value={data.prompt}
            onChange={(e) => setSectionData(section.index, { prompt: e.target.value })}
            size="small"
            fullWidth
            multiline
            rows={2}
            placeholder={section.hint}
            disabled={data.loading}
          />

          <Stack direction="row" spacing={1}>
            <TextField
              label="题材"
              value={genre}
              onChange={(e) => setGenre(e.target.value)}
              size="small"
              sx={{ width: 200 }}
            />
            <Button
              variant="contained"
              size="small"
              startIcon={data.loading ? <CircularProgress size={14} /> : <AutoAwesomeIcon />}
              onClick={() => void handleGenerate(section.index)}
              disabled={data.loading}
            >
              {data.loading ? `生成 ${section.title} 中...` : `生成 ${section.title}`}
            </Button>
            {data.loading && data.taskId && (
              <Button size="small" color="error" onClick={() => void cancel(data.taskId!)}>
                取消
              </Button>
            )}
          </Stack>

          {/* 生成内容 */}
          {data.text && (
            <Box
              sx={{
                p: 2,
                border: 1,
                borderColor: 'success.main',
                borderRadius: 1,
                bgcolor: 'background.paper',
                whiteSpace: 'pre-wrap',
                fontFamily: 'monospace',
                fontSize: 14,
                minHeight: 200,
                maxHeight: 400,
                overflow: 'auto',
              }}
            >
              {data.text}
              {data.loading && <CircularProgress size={14} sx={{ ml: 1, verticalAlign: 'middle' }} />}
            </Box>
          )}

          {/* 导航 */}
          <Divider />
          <Stack direction="row" justifyContent="space-between">
            <Button
              size="small"
              disabled={activeTab === 0}
              onClick={() => setActiveTab((t) => Math.max(0, t - 1))}
            >
              ← 上一节
            </Button>
            <Typography variant="caption" color="text.secondary">
              第 {activeTab + 1} / 8 节
            </Typography>
            <Button
              size="small"
              disabled={activeTab === 7}
              onClick={() => setActiveTab((t) => Math.min(7, t + 1))}
            >
              下一节 →
            </Button>
          </Stack>
        </Stack>
      </CardContent>

      <Divider />
      <Box sx={{ p: 1.5, display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
        <Alert severity={completedCount === 8 ? 'success' : 'info'} sx={{ flex: 1, py: 0 }}>
          <Typography variant="caption">
            {completedCount === 8 ? '全部 8 节已完成，可保存' : `还需 ${8 - completedCount} 节`}
          </Typography>
        </Alert>
        <Button
          size="small"
          variant="contained"
          startIcon={<SaveIcon />}
          onClick={() => {
            const md = buildFullMarkdown();
            onSave(md);
            show(`短篇已拼装（${md.length} 字）`, 'success');
          }}
          disabled={completedCount === 0}
        >
          保存整篇
        </Button>
      </Box>
    </Card>
  );
}
