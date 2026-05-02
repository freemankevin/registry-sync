'use strict';

const translations = {
  en: {
    title: 'Registry Sync',
    subtitle: 'Fast container image mirror service',
    hero: {
      title: 'Registry Sync',
      subtitle: 'Mirror and sync container images from Docker Hub, GHCR, GCR, QUAY and AWS ECR',
      description: 'Fast container image mirror service for better availability and faster pulls'
    },
    stats: {
      totalMirrors: 'Total Mirrors',
      storageSpace: 'Storage Space',
      avgImageSize: 'Avg Image Size',
      latestUpdates: 'Latest Updates',
      availableVersions: 'Available Versions',
      lastSync: 'Last Sync',
      totalSize: 'total size',
      perImage: 'per image',
      updatedThisWeek: 'updated this week',
      thisWeek: 'this week',
      loading: 'loading...',
      failed: 'failed'
    },
    filters: {
      all: 'All',
      dockerHub: 'Docker Hub',
      github: 'GHCR',
      google: 'GCR',
      redhat: 'QUAY',
      aws: 'AWS ECR'
    },
    search: {
      placeholder: 'Search ...',
      ariaLabel: 'Search container images'
    },
    loading: {
      text: 'Loading container images...'
    },
    error: {
      title: 'Failed to load images',
      subtitle: 'Using cached data instead'
    },
    failedSection: {
      title: 'Failed Syncs',
      description: 'These images failed to sync and may not be available'
    },
    card: {
      official: 'official',
      layers: 'layers',
      source: 'Source',
      imageNotSynced: 'Image not synced',
      syncFailed: 'sync failed',
      failed: 'Failed',
      dockerPull: 'docker pull'
    },
    pagination: {
      showing: 'Showing',
      of: 'of',
      total: 'Total'
    },
    empty: {
      title: 'No mirrors found',
      description: 'Try adjusting your search or filters'
    },
    toast: {
      addedToFavorites: 'Added to favorites',
      removedFromFavorites: 'Removed from favorites',
      copied: 'Copied!'
    },
    buttons: {
      theme: {
        dark: 'Dark Mode',
        light: 'Light Mode'
      },
      lang: {
        title: 'Language',
        zh: '中文',
        en: 'EN'
      },
      backToTop: 'Back to top',
      copy: 'Copy pull command',
      github: 'View on GitHub'
    },
    footer: {
      copyright: 'Registry Sync'
    },
    aria: {
      statsSummary: 'Service statistics summary',
      filterByRegistry: 'Filter mirrors by registry',
      mirrorList: 'Container image mirrors',
      failedList: 'Failed container image syncs',
      pagination: 'Pagination navigation',
      mirrorLabel: 'mirror',
      failedLabel: 'sync failed'
    },
    time: {
      ago: {
        m: 'm ago',
        h: 'h ago',
        d: 'd ago',
        mo: 'mo ago'
      },
      failed: 'Failed'
    }
  },
  zh: {
    title: 'Registry Sync',
    subtitle: '快速容器镜像同步服务',
    hero: {
      title: 'Registry Sync',
      subtitle: '镜像同步容器镜像，来自 Docker Hub、GHCR、GCR、QUAY 和 AWS ECR',
      description: '快速容器镜像同步服务，提供更好的可用性和更快的拉取速度'
    },
    stats: {
      totalMirrors: '镜像总数',
      storageSpace: '存储空间',
      avgImageSize: '平均大小',
      latestUpdates: '本周更新',
      availableVersions: '可用版本',
      lastSync: '最近同步',
      totalSize: '总大小',
      perImage: '每个镜像',
      updatedThisWeek: '本周更新',
      thisWeek: '本周',
      loading: '加载中...',
      failed: '失败'
    },
    filters: {
      all: '全部',
      dockerHub: 'Docker Hub',
      github: 'GHCR',
      google: 'GCR',
      redhat: 'Quay',
      aws: 'AWS ECR'
    },
    search: {
      placeholder: '搜索...',
      ariaLabel: '搜索容器镜像'
    },
    loading: {
      text: '正在加载容器镜像...'
    },
    error: {
      title: '加载镜像失败',
      subtitle: '使用缓存数据代替'
    },
    failedSection: {
      title: '同步失败',
      description: '这些镜像同步失败，可能无法使用'
    },
    card: {
      official: '官方',
      layers: '层',
      source: '来源',
      imageNotSynced: '镜像未同步',
      syncFailed: '同步失败',
      failed: '失败',
      dockerPull: 'docker pull'
    },
    pagination: {
      showing: '显示',
      of: '共',
      total: '总计'
    },
    empty: {
      title: '未找到镜像',
      description: '请尝试调整搜索或筛选条件'
    },
    toast: {
      addedToFavorites: '已添加到收藏',
      removedFromFavorites: '已从收藏移除',
      copied: '已复制!'
    },
    buttons: {
      theme: {
        dark: '深色模式',
        light: '浅色模式'
      },
      lang: {
        title: '语言',
        zh: '中文',
        en: 'EN'
      },
      backToTop: '回到顶部',
      copy: '复制拉取命令',
      github: '在 GitHub 上查看'
    },
    footer: {
      copyright: 'Registry Sync'
    },
    aria: {
      statsSummary: '服务统计摘要',
      filterByRegistry: '按镜像源筛选',
      mirrorList: '容器镜像列表',
      failedList: '同步失败的容器镜像',
      pagination: '分页导航',
      mirrorLabel: '镜像',
      failedLabel: '同步失败'
    },
    time: {
      ago: {
        m: '分钟前',
        h: '小时前',
        d: '天前',
        mo: '月前'
      },
      failed: '失败于'
    }
  }
};

let currentLang = localStorage.getItem('lang') || 'en';

function initLang() {
  const saved = localStorage.getItem('lang');
  if (saved && (saved === 'en' || saved === 'zh')) {
    currentLang = saved;
  } else {
    const browserLang = navigator.language || navigator.userLanguage || 'en';
    const isChinese = browserLang.toLowerCase().startsWith('zh');
    currentLang = isChinese ? 'zh' : 'en';
  }
  updateLangButton();
  applyTranslations();
}

function toggleLang() {
  currentLang = currentLang === 'en' ? 'zh' : 'en';
  localStorage.setItem('lang', currentLang);
  updateLangButton();
  applyTranslations();
  if (typeof render === 'function') {
    render();
  }
}

function updateLangButton() {
  const langIcon = document.getElementById('langIcon');
  const langBtn = document.getElementById('langBtn');
  if (langIcon) {
    langIcon.textContent = currentLang === 'en' ? '中文' : 'EN';
  }
  if (langBtn) {
    langBtn.title = currentLang === 'en' ? '切换到中文' : 'Switch to English';
  }
}

function t(key) {
  const keys = key.split('.');
  let value = translations[currentLang];
  for (const k of keys) {
    if (value && typeof value === 'object') {
      value = value[k];
    } else {
      break;
    }
  }
  return value || key;
}

function applyTranslations() {
  const setText = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };

  const setPlaceholder = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.placeholder = text;
  };

  const setTitle = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.title = text;
  };

  const setAriaLabel = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.setAttribute('aria-label', text);
  };

  document.documentElement.lang = currentLang;

  document.title = t('title');

  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const text = t(key);
    if (text && text !== key) {
      el.textContent = text;
    }
  });

  setPlaceholder('searchInput', t('search.placeholder'));
  setAriaLabel('searchInput', t('search.ariaLabel'));

  const loadingText = document.querySelector('#loadingState p');
  if (loadingText) loadingText.textContent = t('loading.text');

  const errorTitle = document.querySelector('#errorState h3');
  if (errorTitle) errorTitle.textContent = t('error.title');
  const errorSub = document.querySelector('#errorState p');
  if (errorSub) errorSub.textContent = t('error.subtitle');

  const failedTitle = document.querySelector('#failedSection h2');
  if (failedTitle) failedTitle.textContent = t('failedSection.title');
  const failedDesc = document.querySelector('#failedSection p');
  if (failedDesc) failedDesc.textContent = t('failedSection.description');

  const emptyTitle = document.querySelector('#emptyState h3');
  if (emptyTitle) emptyTitle.textContent = t('empty.title');
  const emptyDesc = document.querySelector('#emptyState p');
  if (emptyDesc) emptyDesc.textContent = t('empty.description');

  const backToTopBtn = document.getElementById('backToTop');
  if (backToTopBtn) {
    backToTopBtn.setAttribute('aria-label', t('buttons.backToTop'));
    backToTopBtn.title = t('buttons.backToTop');
  }

  updateThemeButtonLang();
}

function updateThemeButtonLang() {
  const themeBtn = document.getElementById('themeBtn');
  if (themeBtn) {
    const isDark = document.documentElement.classList.contains('dark');
    themeBtn.title = isDark ? t('buttons.theme.light') : t('buttons.theme.dark');
  }
}

window.i18n = {
  t,
  get currentLang() { return currentLang; },
  set currentLang(val) { currentLang = val; },
  toggleLang,
  initLang,
  translations
};