export type View = 'home' | 'community' | 'reports';
export type CommunityTab = 'news' | 'forum' | 'models' | 'builder';

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  error?: boolean;
};

export type NewsItem = {
  id?: string;
  headline?: string;
  sentiment?: string;
  teaser?: string;
  stale?: boolean;
  explanation?: {
    what_happened?: string;
    why_it_matters?: string;
    market_reaction?: string;
  };
  source?: {
    name?: string;
    url?: string;
  };
};

export type ForumComment = {
  id: string;
  thread_id: string;
  body: string;
  author: string;
  created_at: string;
};

export type ForumThread = {
  id: string;
  title: string;
  body: string;
  author: string;
  created_at: string;
  score: number;
  upvotes: number;
  downvotes: number;
  comment_count?: number;
  comments?: ForumComment[];
};

export type ModelSeriesPoint = {
  label: string;
  equity: number;
  benchmark: number;
  drawdown: number;
};

export type CommunityModel = {
  id: string;
  name: string;
  author: string;
  summary: string;
  score: number;
  created_at: string;
  tags: string[];
  stats: Record<string, string>;
  code: string;
  ticker?: string;
  profile?: Record<string, string>;
  series?: ModelSeriesPoint[];
  highlights?: string[];
  status?: string;
};

export type BuilderResult = {
  name: string;
  author: string;
  summary: string;
  ticker?: string;
  stats: Record<string, string>;
  profile?: Record<string, string>;
  series?: ModelSeriesPoint[];
  highlights?: string[];
  validation?: Array<{
    label: string;
    status: string;
    detail: string;
  }>;
  notes?: string[];
  status?: string;
};

export type BuilderTemplate = {
  name: string;
  description: string;
  summary: string;
  tags: string[];
  benchmark: string;
  status: string;
  previewStats: Record<string, string>;
  previewProfile: Record<string, string>;
  code: string;
};

export type ShelfItemKind = 'conversation' | 'watchlist' | 'model' | 'model_run';

export type PersonalShelfItem = {
  id: string;
  kind: ShelfItemKind;
  title: string;
  subtitle: string;
  body: string;
  topic?: string;
  created_at: string;
  tags?: string[];
  stats?: Record<string, string>;
};
