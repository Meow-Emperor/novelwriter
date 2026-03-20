import type { legalZhMessages } from '@/lib/uiMessagePacks/legal'
import type { continuationZhMessages, worldModelZhMessages } from '@/lib/uiMessagePacks/novel'

export type UiLocale = 'zh' | 'en'

export type UiMessageParams = Record<string, string | number | boolean | null | undefined>
export type UiMessageValue = string | ((params: UiMessageParams) => string)

const settingsZhMessages = {
  'settings.title': '设置',
  'settings.section.appearance': '外观',
  'settings.section.ai': 'AI 模型配置',
  'settings.section.account': '账户',
  'settings.footer.version': 'NovWr v0.01 Beta',
  'settings.appearance.themeTitle': '主题模式',
  'settings.appearance.theme.dark': '深色模式',
  'settings.appearance.theme.light': '浅色模式',
  'settings.appearance.languageTitle': '界面语言',
  'settings.appearance.languageDescription': '切换受支持产品界面的显示语言。',
  'settings.appearance.language.zh': '简体中文',
  'settings.appearance.language.en': 'English',
  'settings.account.nickname': '昵称',
  'settings.account.remainingQuota': '剩余生成次数',
  'settings.account.feedbackReward': '提交反馈可获得额外生成额度',
  'settings.account.submitFeedback': '提交反馈',
  'settings.account.logout': '退出登录',
} as const satisfies Record<string, UiMessageValue>

const chromeZhMessages = {
  'navbar.features': '功能',
  'navbar.library': '作品库',
  'navbar.settings': '设置',
  'navbar.login': '登录',
  'footer.link.terms': '用户规则',
  'footer.link.privacy': '隐私说明',
  'footer.link.copyright': '版权投诉',
  'footer.description': '面向长篇创作的 AI 辅助写作与续写工具。使用本服务前，请阅读相关规则、隐私说明与版权投诉说明。',
  'dialog.confirm': '确认',
  'dialog.cancel': '取消',
  'dialog.gotIt': '知道了',
} as const satisfies Record<string, UiMessageValue>

const homeZhMessages = {
  'home.hero.title': '在完整的世界观里续写你的故事',
  'home.hero.description': 'NovWr 通过世界模型驱动 AI 续写——不是盲目生成，而是真正理解你笔下的角色、关系与规则，写出连贯的长篇故事。',
  'home.hero.cta': '开始写作',
  'home.features.title': '核心能力',
  'home.features.description': '不只是文本生成器——NovWr 让 AI 真正理解你的故事世界',
  'home.features.worldModel.title': '世界模型',
  'home.features.worldModel.description': '构建角色、关系、规则体系——AI 基于结构化知识图谱理解你的世界，而非简单的上下文窗口。',
  'home.features.continuation.title': '语境感知续写',
  'home.features.continuation.description': '不是盲目生成，而是基于世界模型的连贯写作。AI 知道谁在哪里、发生了什么、规则是什么。',
  'home.features.compare.title': '多版本对比',
  'home.features.compare.description': '一次生成多个续写版本，对比选择最佳方案。快速迭代，找到最契合故事走向的那一版。',
  'home.cta.title': '开始构建你的故事世界',
  'home.cta.description': '让 AI 成为你的共创伙伴，而不只是一个文本生成器。',
  'home.cta.button': '免费开始写作',
} as const satisfies Record<string, UiMessageValue>

const loginZhMessages = {
  'login.header.hosted': '使用 GitHub 或邀请码开始体验',
  'login.header.selfhost': '登录到你的账户',
  'login.oauth.githubNotConfigured': 'GitHub 登录暂未配置，请稍后再试。',
  'login.oauth.stateInvalid': '登录状态已失效，请重新点击 GitHub 登录。',
  'login.oauth.accessDenied': '你已取消 GitHub 授权，未完成登录。',
  'login.oauth.signupBlocked': '当前暂不接受新的 GitHub 注册，请稍后再试。',
  'login.oauth.accountDisabled': '该账户已被停用，请联系管理员。',
  'login.oauth.failed': 'GitHub 登录失败，请稍后重试。',
  'login.github.button': '使用 GitHub 登录',
  'login.invite.or': '或使用邀请码',
  'login.invite.code.label': '邀请码',
  'login.invite.code.placeholder': '从 Linux.do 帖子获取',
  'login.invite.nickname.label': '昵称',
  'login.invite.nickname.placeholder': '你的显示名称',
  'login.username.label': '用户名',
  'login.password.label': '密码',
  'login.submit.loading': '请稍候...',
  'login.submit.hosted': '开始体验',
  'login.submit.selfhost': '登录',
  'login.requestIdSuffix': ({ requestId }) => `（Request ID: ${String(requestId ?? '')}）`,
  'login.alert.invalidInvite.title': '邀请码无效',
  'login.alert.invalidInvite.description': '请检查邀请码是否正确',
  'login.alert.signupBlocked.title': '注册已暂停',
  'login.alert.signupBlocked.description': '当前暂不接受新的注册，请稍后再试',
  'login.alert.invalidCredentials.title': '登录失败',
  'login.alert.invalidCredentials.description': '用户名或密码错误',
  'login.alert.backend404.title': '连接失败',
  'login.alert.backend404.description': '无法连接到后端（/api 404）。如果你在 WSL + Windows 浏览器开发，请确认后端已启动，并重启前端 dev server 以生效 Vite /api 代理。',
  'login.alert.httpFailure.title': '操作失败',
  'login.alert.httpFailure.description': ({ status }) => `请求失败（HTTP ${String(status ?? '')}）。请稍后重试`,
  'login.alert.network.title': '连接失败',
  'login.alert.network.description': '无法连接到后端，请确认后端已启动（以及前端是否通过 /api 代理）。',
} as const satisfies Record<string, UiMessageValue>

const libraryZhMessages = {
  'library.create': '新建作品',
  'library.title': '我的作品库',
  'library.description': '管理你的所有小说作品',
  'library.error.load': '加载失败',
  'library.error.unknown': '未知错误',
  'library.error.uploadFailed': '上传失败',
  'library.confirm.delete': '确定要删除这部作品吗？此操作不可撤销。',
  'library.empty.title': '还没有作品，开始创作你的第一部小说吧',
  'library.workCard.meta': ({ chapterCount, relativeTime }) => `${String(chapterCount ?? 0)} 章 · ${String(relativeTime ?? '')}更新`,
  'library.workCard.delete': '删除',
} as const satisfies Record<string, UiMessageValue>

const relativeTimeZhMessages = {
  'time.justNow': '刚刚',
  'time.minutesAgo': ({ count }) => `${String(count ?? 0)} 分钟前`,
  'time.hoursAgo': ({ count }) => `${String(count ?? 0)} 小时前`,
  'time.yesterday': '昨天',
  'time.daysAgo': ({ count }) => `${String(count ?? 0)} 天前`,
  'time.weeksAgo': ({ count }) => `${String(count ?? 0)} 周前`,
  'time.monthsAgo': ({ count }) => `${String(count ?? 0)} 月前`,
} as const satisfies Record<string, UiMessageValue>

const llmZhMessages = {
  'llm.notice.hosted': '在线版也支持填写你自己的 API Key，但请先知晓风险：密钥会在模型请求时通过当前实例服务器转发到你配置的 OpenAI 兼容接口。当前实现不会把这类用户自带密钥持久化到浏览器或服务端；它只保留在当前标签页内存里，刷新页面后会清空。如果你对当前部署实例的运维环境不完全信任，建议不要在在线版填写，改用 Docker 自部署。',
  'llm.notice.selfhost': '出于安全考虑，这里的配置只保留在当前浏览器标签页内存中；刷新页面后会清空。如果你想长期使用自己的 Key，推荐改用 Docker / 环境变量自部署。',
  'llm.warning.partialConfig': '当前只填写了部分 BYOK 配置。请同时填写 Base URL、API Key 和 Model；否则续写、世界生成和提取都会被拒绝。',
  'llm.error.incompleteConfig': '当前 BYOK 配置不完整，请同时填写 Base URL、API Key 和 Model，或清空当前配置。',
  'llm.error.aiDisabled': '当前实例已关闭 AI 功能，暂时无法发起模型请求。',
  'llm.error.budgetHardStop': '当前实例的托管 AI 额度已达上限，请稍后再试，或改用你自己的 API Key。',
  'llm.error.budgetUnavailable': '当前实例暂时关闭了托管 AI 请求，请稍后再试，或改用你自己的 API Key。',
  'llm.error.modelUnavailable': '当前模型不可用。请检查 Base URL、API Key、Model 是否匹配，并确认接口支持 JSON 模式。',
  'llm.result.successFallback': ({ latencyMs }) => `连接与应用兼容性检测通过 (${String(latencyMs ?? '')}ms)`,
  'llm.result.connectionFailed': '连接失败',
  'llm.result.httpFailed': ({ status }) => `请求失败（HTTP ${String(status ?? '')}）`,
  'llm.label.baseUrl': 'API Base URL',
  'llm.label.apiKey': 'API Key',
  'llm.label.model': 'Model Name',
  'llm.button.testing': '测试中...',
  'llm.button.test': '测试连接',
  'llm.button.clear': '清空当前标签页配置',
} as const satisfies Record<string, UiMessageValue>

const feedbackZhMessages = {
  'feedback.title': '使用反馈',
  'feedback.description': '填写以下反馈即可获得额外生成额度。你的反馈对我们非常重要。',
  'feedback.question.rating': '1. 整体体验如何？',
  'feedback.question.issues': '2. 遇到了什么问题？（可多选）',
  'feedback.question.suggestion': '3. 改进建议（可选）',
  'feedback.rating.great': '很好，超出预期',
  'feedback.rating.good': '还不错，有潜力',
  'feedback.rating.okay': '一般，需要改进',
  'feedback.rating.poor': '不太行，问题较多',
  'feedback.issue.speed': '生成速度太慢',
  'feedback.issue.quality': '生成文本质量不够好',
  'feedback.issue.ux': '操作流程不够直观',
  'feedback.issue.bugs': '遇到了 Bug',
  'feedback.issue.other': '其他问题',
  'feedback.issue.none': '暂时没有明显问题',
  'feedback.placeholder.bug': '简要描述一下遇到的 Bug，例如：上传小说后页面白屏',
  'feedback.placeholder.other': '具体是什么问题？',
  'feedback.placeholder.suggestion': '有什么想法或建议？',
  'feedback.bonus.max': '提交可获得 30 次额度',
  'feedback.bonus.upgrade': '填写不少于 20 字的建议，额度从 20 次提升至 30 次',
  'feedback.submit.loading': '提交中...',
  'feedback.submit.button': ({ count }) => `提交反馈，获得 ${String(count ?? 20)} 次额度`,
} as const satisfies Record<string, UiMessageValue>

const zhMessages = {
  ...settingsZhMessages,
  ...chromeZhMessages,
  ...homeZhMessages,
  ...loginZhMessages,
  ...libraryZhMessages,
  ...relativeTimeZhMessages,
  ...llmZhMessages,
  ...feedbackZhMessages,
} as const satisfies Record<string, UiMessageValue>

type UiMessageCatalog = typeof zhMessages & typeof worldModelZhMessages & typeof continuationZhMessages & typeof legalZhMessages

export type UiMessageKey = Extract<keyof UiMessageCatalog, string>

const enMessages: Partial<Record<UiMessageKey, UiMessageValue>> = {
  'settings.title': 'Settings',
  'settings.section.appearance': 'Appearance',
  'settings.section.ai': 'AI model config',
  'settings.section.account': 'Account',
  'settings.footer.version': 'NovWr v0.01 Beta',
  'settings.appearance.themeTitle': 'Theme mode',
  'settings.appearance.theme.dark': 'Dark mode',
  'settings.appearance.theme.light': 'Light mode',
  'settings.appearance.languageTitle': 'Interface language',
  'settings.appearance.languageDescription': 'Choose the display language for supported product surfaces.',
  'settings.appearance.language.zh': '简体中文',
  'settings.appearance.language.en': 'English',
  'settings.account.nickname': 'Nickname',
  'settings.account.remainingQuota': 'Remaining generations',
  'settings.account.feedbackReward': 'Submit feedback to unlock extra generation quota',
  'settings.account.submitFeedback': 'Submit feedback',
  'settings.account.logout': 'Log out',

  'navbar.features': 'Features',
  'navbar.library': 'Library',
  'navbar.settings': 'Settings',
  'navbar.login': 'Log in',
  'footer.link.terms': 'Terms of use',
  'footer.link.privacy': 'Privacy notice',
  'footer.link.copyright': 'Copyright notice',
  'footer.description': 'An AI-assisted writing and continuation tool for long-form fiction. Please read the terms, privacy notice, and copyright notice before using the service.',
  'dialog.confirm': 'Confirm',
  'dialog.cancel': 'Cancel',
  'dialog.gotIt': 'Got it',

  'home.hero.title': 'Continue your story inside a complete world model',
  'home.hero.description': 'NovWr uses a world model to drive AI continuation—not blind text generation, but long-form writing that actually understands your characters, relationships, and rules.',
  'home.hero.cta': 'Start writing',
  'home.features.title': 'Core capabilities',
  'home.features.description': 'More than a text generator—NovWr helps AI truly understand your story world',
  'home.features.worldModel.title': 'World model',
  'home.features.worldModel.description': 'Build characters, relationships, and rule systems so the AI reasons over structured knowledge instead of a shallow context window.',
  'home.features.continuation.title': 'Context-aware continuation',
  'home.features.continuation.description': 'Not blind generation, but coherent continuation grounded in the world model. The AI knows who is where, what happened, and which rules apply.',
  'home.features.compare.title': 'Multi-version comparison',
  'home.features.compare.description': 'Generate multiple continuation candidates at once, compare them quickly, and keep the version that best fits your story.',
  'home.cta.title': 'Start building your story world',
  'home.cta.description': 'Let AI become your co-writing partner, not just a text generator.',
  'home.cta.button': 'Start writing for free',

  'login.header.hosted': 'Use GitHub or an invite code to get started',
  'login.header.selfhost': 'Sign in to your account',
  'login.oauth.githubNotConfigured': 'GitHub sign-in is not configured yet. Please try again later.',
  'login.oauth.stateInvalid': 'Your login state expired. Please click GitHub sign-in again.',
  'login.oauth.accessDenied': 'You canceled GitHub authorization, so sign-in was not completed.',
  'login.oauth.signupBlocked': 'New GitHub sign-ups are currently paused. Please try again later.',
  'login.oauth.accountDisabled': 'This account has been disabled. Please contact the administrator.',
  'login.oauth.failed': 'GitHub sign-in failed. Please try again later.',
  'login.github.button': 'Continue with GitHub',
  'login.invite.or': 'or use an invite code',
  'login.invite.code.label': 'Invite code',
  'login.invite.code.placeholder': 'Get one from the Linux.do post',
  'login.invite.nickname.label': 'Nickname',
  'login.invite.nickname.placeholder': 'Your display name',
  'login.username.label': 'Username',
  'login.password.label': 'Password',
  'login.submit.loading': 'Please wait...',
  'login.submit.hosted': 'Get started',
  'login.submit.selfhost': 'Log in',
  'login.requestIdSuffix': ({ requestId }) => ` (Request ID: ${String(requestId ?? '')})`,
  'login.alert.invalidInvite.title': 'Invalid invite code',
  'login.alert.invalidInvite.description': 'Please check whether the invite code is correct',
  'login.alert.signupBlocked.title': 'Sign-ups are paused',
  'login.alert.signupBlocked.description': 'New registrations are currently unavailable. Please try again later',
  'login.alert.invalidCredentials.title': 'Sign-in failed',
  'login.alert.invalidCredentials.description': 'Incorrect username or password',
  'login.alert.backend404.title': 'Connection failed',
  'login.alert.backend404.description': 'The frontend could not reach the backend (/api returned 404). If you develop with WSL + a Windows browser, make sure the backend is running, then restart the frontend dev server so the Vite /api proxy takes effect.',
  'login.alert.httpFailure.title': 'Request failed',
  'login.alert.httpFailure.description': ({ status }) => `The request failed (HTTP ${String(status ?? '')}). Please try again later`,
  'login.alert.network.title': 'Connection failed',
  'login.alert.network.description': 'The frontend could not reach the backend. Please make sure the backend is running and that the frontend is using the /api proxy.',

  'library.create': 'New novel',
  'library.title': 'Library',
  'library.description': 'Manage all of your novels',
  'library.error.load': 'Failed to load',
  'library.error.unknown': 'Unknown error',
  'library.error.uploadFailed': 'Upload failed',
  'library.confirm.delete': 'Delete this novel? This action cannot be undone.',
  'library.empty.title': 'No novels yet—start writing your first one.',
  'library.workCard.meta': ({ chapterCount, relativeTime }) => `${String(chapterCount ?? 0)} ${Number(chapterCount) === 1 ? 'chapter' : 'chapters'} · updated ${String(relativeTime ?? '')}`,
  'library.workCard.delete': 'Delete',

  'time.justNow': 'just now',
  'time.minutesAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'minute' : 'minutes'} ago`,
  'time.hoursAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'hour' : 'hours'} ago`,
  'time.yesterday': 'yesterday',
  'time.daysAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'day' : 'days'} ago`,
  'time.weeksAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'week' : 'weeks'} ago`,
  'time.monthsAgo': ({ count }) => `${String(count ?? 0)} ${Number(count) === 1 ? 'month' : 'months'} ago`,

  'llm.notice.hosted': 'The hosted app also lets you use your own API key, but understand the risk first: when you send model requests, the key is proxied through this instance to the OpenAI-compatible endpoint you configured. The current implementation does not persist user-provided keys in the browser or on the server; it only keeps them in the current tab’s memory and clears them on refresh. If you do not fully trust the operator of this deployment, avoid entering your key here and use Docker self-hosting instead.',
  'llm.notice.selfhost': 'For safety, this configuration is kept only in the current browser tab’s memory and is cleared on refresh. If you want to use your own key long-term, self-host with Docker or environment variables instead.',
  'llm.warning.partialConfig': 'Only part of the BYOK config is filled in. Provide Base URL, API Key, and Model together; otherwise continuation, world generation, and extraction will be rejected.',
  'llm.error.incompleteConfig': 'The current BYOK config is incomplete. Fill in Base URL, API Key, and Model together, or clear the current config.',
  'llm.error.aiDisabled': 'AI is disabled on this instance, so model requests are unavailable right now.',
  'llm.error.budgetHardStop': 'This instance has exhausted its hosted AI budget. Please try again later or switch to your own API key.',
  'llm.error.budgetUnavailable': 'Hosted AI requests are temporarily unavailable on this instance. Please try again later or switch to your own API key.',
  'llm.error.modelUnavailable': 'The current model is unavailable. Check that Base URL, API Key, and Model match and that the endpoint supports JSON mode.',
  'llm.result.successFallback': ({ latencyMs }) => `Connection and compatibility check passed (${String(latencyMs ?? '')}ms)`,
  'llm.result.connectionFailed': 'Connection failed',
  'llm.result.httpFailed': ({ status }) => `Request failed (HTTP ${String(status ?? '')})`,
  'llm.label.baseUrl': 'API Base URL',
  'llm.label.apiKey': 'API Key',
  'llm.label.model': 'Model name',
  'llm.button.testing': 'Testing...',
  'llm.button.test': 'Test connection',
  'llm.button.clear': 'Clear current tab config',

  'feedback.title': 'Product feedback',
  'feedback.description': 'Submit the form below to earn extra generation quota. Your feedback helps us a lot.',
  'feedback.question.rating': '1. How was the overall experience?',
  'feedback.question.issues': '2. What issues did you run into? (Multiple choice)',
  'feedback.question.suggestion': '3. Improvement ideas (optional)',
  'feedback.rating.great': 'Great, exceeded expectations',
  'feedback.rating.good': 'Pretty good, promising',
  'feedback.rating.okay': 'Average, needs work',
  'feedback.rating.poor': 'Not great, too many problems',
  'feedback.issue.speed': 'Generation is too slow',
  'feedback.issue.quality': 'Text quality is not good enough',
  'feedback.issue.ux': 'The workflow is not intuitive enough',
  'feedback.issue.bugs': 'I hit a bug',
  'feedback.issue.other': 'Other issue',
  'feedback.issue.none': 'No obvious issue for now',
  'feedback.placeholder.bug': 'Briefly describe the bug, for example: the page turned blank after uploading a novel',
  'feedback.placeholder.other': 'What exactly went wrong?',
  'feedback.placeholder.suggestion': 'Any ideas or suggestions?',
  'feedback.bonus.max': 'Submit now to get 30 extra generations',
  'feedback.bonus.upgrade': 'Write at least 20 characters of suggestions to raise the reward from 20 to 30 generations',
  'feedback.submit.loading': 'Submitting...',
  'feedback.submit.button': ({ count }) => `Submit feedback and get ${String(count ?? 20)} extra generations`,

}

export const uiMessages: Record<UiLocale, Partial<Record<UiMessageKey, UiMessageValue>>> = {
  zh: { ...zhMessages },
  en: { ...enMessages },
}

const registeredUiMessagePacks = new Set<object>()

export function registerUiMessages(
  messages: Record<UiLocale, Partial<Record<UiMessageKey, UiMessageValue>>>,
): void {
  if (registeredUiMessagePacks.has(messages)) return
  registeredUiMessagePacks.add(messages)
  Object.assign(uiMessages.zh, messages.zh)
  Object.assign(uiMessages.en, messages.en)
}

function renderUiMessage(
  value: UiMessageValue,
  params: UiMessageParams | undefined,
): string {
  if (typeof value === 'function') {
    return value(params ?? {})
  }
  return value
}

export function translateUiMessage(
  locale: UiLocale,
  key: UiMessageKey,
  params?: UiMessageParams,
): string {
  const value = uiMessages[locale][key] ?? uiMessages.zh[key]
  if (value) return renderUiMessage(value, params)
  return `[missing:${String(key)}]`
}
