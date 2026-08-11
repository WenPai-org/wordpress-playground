/** WenPai shell locale policy. WordPress instance locale uses `language`. */
export const DEFAULT_UI_LANGUAGE = 'zh_CN' as const;
export const DEFAULT_WORDPRESS_LANGUAGE = 'zh_CN' as const;
export const UI_LANGUAGE_QUERY_PARAMETER = 'ui-language' as const;
export const WORDPRESS_LANGUAGE_QUERY_PARAMETER = 'language' as const;

const CHINESE_UI_LANGUAGE_ALIASES = new Set(['zh', 'zh-cn', 'zh_cn']);

export function resolveUiLanguage(
	search: string | URLSearchParams = window.location.search
): typeof DEFAULT_UI_LANGUAGE {
	const params =
		typeof search === 'string' ? new URLSearchParams(search) : search;
	const requested = params.get(UI_LANGUAGE_QUERY_PARAMETER)?.toLowerCase();
	return !requested || CHINESE_UI_LANGUAGE_ALIASES.has(requested)
		? DEFAULT_UI_LANGUAGE
		: DEFAULT_UI_LANGUAGE;
}

export function applyProductLocale(): typeof DEFAULT_UI_LANGUAGE {
	const locale = resolveUiLanguage();
	document.documentElement.lang = 'zh-CN';
	document.documentElement.dataset.uiLanguage = locale;
	return locale;
}
