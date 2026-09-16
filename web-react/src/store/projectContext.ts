/**
 * ProjectContext store — 多项目切换（Sprint 5 第 2 批）
 *
 * 用途:
 *   - 保存当前激活的项目路径（currentProject.path）
 *   - 切换项目时 invalidate 所有依赖项目数据的 query cache
 *   - localStorage 持久化（key: 'n2a.currentProject'）
 *
 * 设计:
 *   - currentProject: { path, name } | null
 *   - default: null（未选择项目，page 自己用 project_root='.' 作为 fallback）
 *   - 切换: setCurrentProject(project) + invalidateAll()
 *
 * 与 useUserProjects 配合:
 *   - admin: useUserProjects(userId) 拿任意用户项目
 *   - 普通用户: useUserProjects(me.user.id) 拿自己的项目
 *   - 切换: 直接 setCurrentProject 即可（不需要重登）
 */

import { create } from 'zustand';
import { useQueryClient } from '@tanstack/react-query';

export interface ProjectContext {
  /** 项目根路径（用作 API project_root 参数） */
  path: string;
  /** 友好显示名（默认等于 path basename） */
  name?: string;
  /** 分享权限（用于决定 UI 是否显示 share 按钮） */
  role?: 'admin' | 'editor' | 'viewer';
}

const STORAGE_KEY = 'n2a.currentProject';

function loadInitial(): ProjectContext | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ProjectContext;
    if (typeof parsed?.path === 'string') return parsed;
  } catch {
    /* 忽略 */
  }
  return null;
}

function persist(project: ProjectContext | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (project) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(project));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    /* 忽略 */
  }
}

interface ProjectContextState {
  currentProject: ProjectContext | null;
  setCurrentProject: (project: ProjectContext | null) => void;
  clearCurrentProject: () => void;
}

export const useProjectContextStore = create<ProjectContextState>((set) => ({
  currentProject: loadInitial(),
  setCurrentProject: (project) => {
    persist(project);
    set({ currentProject: project });
  },
  clearCurrentProject: () => {
    persist(null);
    set({ currentProject: null });
  },
}));

/**
 * useCurrentProject — 统一访问当前项目（page 端用法）
 *
 * 行为:
 *   - 优先返回 store 中的 currentProject
 *   - 如果为 null，回退到默认值 { path: '.', name: '默认项目' }
 *   - 这样不需要 page 自己处理 "未选择项目" 的边缘情况
 */
export function useCurrentProject(): ProjectContext {
  const current = useProjectContextStore((s) => s.currentProject);
  return current ?? { path: '.', name: '默认项目' };
}

/**
 * useProjectSwitch — 切换项目并 invalidate 所有相关 query
 *
 * 用法:
 *   const { switchProject, isSwitching } = useProjectSwitch();
 *   switchProject(project);
 */
export function useProjectSwitch(): {
  switchProject: (project: ProjectContext) => void;
  isReady: boolean;
} {
  const qc = useQueryClient();
  const setCurrentProject = useProjectContextStore((s) => s.setCurrentProject);

  return {
    switchProject: (project) => {
      // 1. 切换 store
      setCurrentProject(project);
      // 2. invalidate 所有依赖 project 的 query
      //    章节 / status / skills / cache / audit 等都依赖 projectRoot
      void qc.invalidateQueries({ queryKey: ['status'] });
      void qc.invalidateQueries({ queryKey: ['chapters'] });
      void qc.invalidateQueries({ queryKey: ['chapter'] });
      void qc.invalidateQueries({ queryKey: ['cache'] });
      void qc.invalidateQueries({ queryKey: ['roles'] });
      void qc.invalidateQueries({ queryKey: ['auth', 'user-projects'] });
    },
    isReady: true,
  };
}
