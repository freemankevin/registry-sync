/* ============================================
   Registry Sync — app.js
   ============================================ */

'use strict';

// ── State ──────────────────────────────────────
let itemsPerPage = parseInt(localStorage.getItem('itemsPerPage')) || 10;
let allImages    = [];   // flat list of display objects
let imageData    = {};   // name → full record (with versions[])
let failedImages = [];   // failed images list
let currentFilter = 'all';
let currentSearch = '';
let currentPage   = 1;

function getLocalizedDescription(img) {
  const lang = window.i18n ? window.i18n.currentLang : 'en';
  if (lang === 'zh' && img.description_zh) {
    return img.description_zh;
  }
  return img.description || '';
}

function getSourceType(img) {
  const src = (img.source || img.name || '').toLowerCase();
  if (src.startsWith('gcr.io/')   || src.startsWith('us.gcr.io/') ||
      src.startsWith('k8s.gcr.io/') || src.startsWith('registry.k8s.io/')) return 'google';
  if (src.startsWith('quay.io/') || src.includes('redhat'))                 return 'redhat';
  if (src.startsWith('ghcr.io/'))                                            return 'github';
  if (src.startsWith('public.ecr.aws/'))                                     return 'aws';
  return 'dockerhub';
}

function getSourceLabel(type) {
  return { dockerhub:'#dockerhub', github:'#ghcr', google:'#gcr', redhat:'#quay', aws:'#aws' }[type] || '#dockerhub';
}

// ── Theme ─────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem('theme');
  const dark  = saved ? saved === 'dark' : window.matchMedia('(prefers-color-scheme:dark)').matches;
  document.documentElement.classList.remove('dark', 'light');
  document.documentElement.classList.add(dark ? 'dark' : 'light');
  updateThemeIcon(dark);
}

function toggleTheme() {
  const isDark = document.documentElement.classList.contains('dark');
  document.documentElement.classList.remove('dark', 'light');
  const newDark = !isDark;
  document.documentElement.classList.add(newDark ? 'dark' : 'light');
  localStorage.setItem('theme', newDark ? 'dark' : 'light');
  updateThemeIcon(newDark);
}

function updateThemeIcon(isDark) {
  const icon = document.getElementById('themeIcon');
  const btn = document.getElementById('themeBtn');
  if (icon) {
    icon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
  }
  if (btn) {
    btn.title = isDark ? 'Light Mode' : 'Dark Mode';
  }
}

// ── Data loading ──────────────────────────────
async function loadImages() {
  try {
    const res = await fetch('/images.json');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    processData(data);
  } catch (e) {
    // Use sample data so UI renders
    processData(sampleData());
  }
}

function processData(data) {
  imageData = {};
  allImages = [];
  failedImages = [];

  const records = Array.isArray(data) ? data : (data.images || Object.values(data));
  const failedRecords = data.failed_images || [];

  records.forEach(img => {
    const name = img.name || img.image || '';
    if (!name) return;

    const versions = img.versions || [];
    const latestVer = img.latest_version || img.version || (versions[0] && (versions[0].version || versions[0].tag)) || 'latest';
    const latestSrc = (versions[0] && versions[0].source) || img.source || (name.startsWith('ghcr.io/') || name.startsWith('gcr.io/') || name.startsWith('quay.io/') ? name : '');
    const latestSize = (versions[0] && versions[0].size) || img.size || '';
    const latestTarget = (versions[0] && versions[0].target) || '';

    const stars = Number(img.stars || img.pulls || 0);
    const layers = Number(img.layers || 0);

    const sourceType = getSourceType({ source: latestSrc, name: name });
    
    const record = {
      name,
      displayName: getDisplayName(name),
      description: img.description || '',
      description_zh: img.description_zh || '',
      stars,
      layers,
      updated:     img.updated || img.last_updated || img.synced_at || '',
      platforms:   img.platforms || img.architectures || ['AMD64','ARM64'],
      official:    isOfficial(name, sourceType),
      source:      latestSrc,
      sourceType:  sourceType,
      size:        latestSize,
      currentVersion: latestVer,
      versions,
      syncStatus: img.sync_status || 'success'
    };

    imageData[name] = record;
    allImages.push(record);
  });

  // Process failed images
  failedRecords.forEach(img => {
    const name = img.name || '';
    if (!name) return;

    const sourceType = getSourceType({ source: img.source || '', name: name });
    
    const record = {
      name,
      displayName: getDisplayName(name),
      description: img.description || '',
      description_zh: img.description_zh || '',
      source: img.source || '',
      sourceType: sourceType,
      version: img.version || '',
      syncStatus: 'failed',
      failedAt: img.failed_at || ''
    };

    failedImages.push(record);
  });

  // Hide loading and error states
  const loadingEl = document.getElementById('loadingState');
  if (loadingEl) loadingEl.classList.add('hidden');
  const errorEl = document.getElementById('errorState');
  if (errorEl) errorEl.classList.add('hidden');

  render();
}

// ── Helpers ───────────────────────────────────
const OFFICIAL_IMAGES = [
  'nacos/nacos-server',
  'kartoza/geoserver',
  'library/nginx',
  'library/redis',
  'library/rabbitmq',
  'library/elasticsearch',
  'library/mariadb',
  'library/postgres',
  'library/mysql',
  'library/mongo',
  'library/python',
  'library/node',
  'library/java',
  'library/ubuntu',
  'library/debian',
  'library/alpine',
  'library/centos',
  'library/redis',
  'library/golang',
  'library/rust',
  'library/php',
  'library/ruby',
  'gcr.io/google-containers/etcd',
  'quay.io/minio/aistor/minio',
  'public.ecr.aws/amazoncorretto/amazoncorretto'
];

const DISPLAY_NAME_MAP = {
  'nacos-server': 'Nacos Server',
  'geoserver': 'GeoServer',
  'nginx': 'Nginx',
  'redis': 'Redis',
  'rabbitmq': 'RabbitMQ',
  'elasticsearch': 'Elasticsearch',
  'mariadb': 'MariaDB',
  'postgres': 'PostgreSQL',
  'postgresql': 'PostgreSQL',
  'mysql': 'MySQL',
  'mongo': 'MongoDB',
  'mongodb': 'MongoDB',
  'python': 'Python',
  'node': 'Node.js',
  'java': 'Java',
  'openjdk': 'OpenJDK',
  'ubuntu': 'Ubuntu',
  'debian': 'Debian',
  'alpine': 'Alpine',
  'centos': 'CentOS',
  'golang': 'Go',
  'rust': 'Rust',
  'php': 'PHP',
  'ruby': 'Ruby',
  'minio': 'MinIO',
  'etcd': 'etcd',  // etcd official name is lowercase
  'amazoncorretto': 'Amazon Corretto',
  'netkit': 'NetKit',
  'postgresql-postgis': 'PostgreSQL PostGIS',
  'postgresql-backup': 'PostgreSQL Backup'
};

function getDisplayName(name) {
  const parts = name.split('/');
  const rawName = parts[parts.length - 1];
  
  // Check if we have a custom display name mapping
  if (DISPLAY_NAME_MAP[rawName]) {
    return DISPLAY_NAME_MAP[rawName];
  }
  
  // Otherwise, capitalize first letter
  return rawName.charAt(0).toUpperCase() + rawName.slice(1);
}

function isOfficial(name, sourceType) {
  // Check if image is in official list
  if (OFFICIAL_IMAGES.includes(name)) {
    return true;
  }
  
  // Docker Hub library images are official
  if (sourceType === 'dockerhub' && (name.startsWith('library/') || !name.includes('/'))) {
    return true;
  }
  
  return false;
}

function formatAgo(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr;
  const mins  = Math.round((Date.now() - d) / 60000);
  const lang = window.i18n ? window.i18n.currentLang : 'en';
  const ago = lang === 'zh' ? window.i18n.translations.zh.time.ago : window.i18n.translations.en.time.ago;
  if (mins < 60)    return mins + ago.m;
  const hrs = Math.round(mins / 60);
  if (hrs < 24)     return hrs + ago.h;
  const days = Math.round(hrs / 24);
  if (days < 30)    return days + ago.d;
  const mos  = Math.round(days / 30);
  return mos + ago.mo;
}

function formatSize(bytes) {
  if (!bytes && bytes !== 0) return '';
  if (typeof bytes === 'string') return bytes;
  if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + ' GB';
  if (bytes >= 1e6) return (bytes / 1e6).toFixed(0) + ' MB';
  if (bytes >= 1e3) return (bytes / 1e3).toFixed(0) + ' KB';
  return bytes + ' B';
}

function parseSizeToMB(sizeStr) {
  if (!sizeStr) return 0;
  if (typeof sizeStr === 'number') return sizeStr / 1e6;
  const s = sizeStr.trim().toUpperCase();
  const match = s.match(/^([\d.]+)\s*(B|KB|MB|GB|TB)$/);
  if (!match) return 0;
  const val = parseFloat(match[1]);
  const unit = match[2];
  const map = { B: 1e-6, KB: 1e-3, MB: 1, GB: 1e3, TB: 1e6 };
  return val * (map[unit] || 0);
}

function animateStatValue(elementId, target, duration = 800) {
  const el = document.getElementById(elementId);
  if (!el || typeof target !== 'number') return;

  let current = parseFloat(el.textContent) || 0;
  if (current === target) return;

  const start = current;
  const startTime = performance.now();

  const step = (now) => {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = progress < 0.5
      ? 2 * progress * progress
      : 1 - Math.pow(-2 * progress + 2, 2) / 2; // ease-out quad

    current = start + (target - start) * eased;
    el.textContent = Number.isInteger(target) ? Math.round(current) : current.toFixed(1);

    if (progress < 1) {
      requestAnimationFrame(step);
    } else {
      el.textContent = Number.isInteger(target) ? target : target.toFixed(1);
    }
  };

  requestAnimationFrame(step);
}

// ── Filtering ─────────────────────────────────
function getFiltered() {
  return allImages.filter(img => {
    if (currentFilter !== 'all' && img.sourceType !== currentFilter) return false;
    if (currentSearch) {
      const q = currentSearch.toLowerCase().trim();
      // 构建完整的镜像路径用于搜索
      const { path: mirrorPath, ver: version } = buildPullCmd(img);
      const fullMirrorPath = `${mirrorPath}:${version}`.toLowerCase();
      const sourcePath = (img.source || '').toLowerCase();
      
      // 检查各个字段是否匹配
      const searchableFields = [
        img.displayName.toLowerCase(),
        img.description.toLowerCase(),
        (img.description_zh || '').toLowerCase(),
        img.name.toLowerCase(),
        fullMirrorPath,
        sourcePath,
        version.toLowerCase()
      ];
      
      // 支持多种匹配方式：
      // 1. 完整镜像路径搜索（如 ghcr.io/freemankevin/library__elasticsearch:9.3.0）
      // 2. 源镜像搜索（如 docker.io/library/elasticsearch）
      // 3. 名称/描述/标签模糊匹配
      const matches = searchableFields.some(field => {
        if (!field) return false;
        // 完全包含匹配
        if (field.includes(q)) return true;
        // 忽略特殊字符的匹配（如 ghcr.io/freemankevin/library__elasticsearch 可以匹配 library__elasticsearch 或 library/elasticsearch）
        const normalizedField = field.replace(/[:_\/\-]/g, '').toLowerCase();
        const normalizedQuery = q.replace(/[:_\/\-]/g, '').toLowerCase();
        if (normalizedField.includes(normalizedQuery)) return true;
        // 关键词分词匹配（空格分隔的多个关键词）
        const keywords = q.split(/\s+/).filter(k => k.length > 0);
        if (keywords.length > 1) {
          return keywords.every(keyword => {
            const normKeyword = keyword.replace(/[:_\/\-]/g, '');
            return field.includes(keyword) || normalizedField.includes(normKeyword);
          });
        }
        return false;
      });
      
      if (!matches) return false;
    }
    return true;
  });
}

function setFilter(f) {
  currentFilter = f;
  currentPage   = 1;
  document.querySelectorAll('.filter-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.filter === f);
  });
  render();
}

function handleSearch(val) {
  currentSearch = val.trim();
  currentPage   = 1;
  render();
}

// ── Stats ─────────────────────────────────────
function updateStats() {
  const t = window.i18n ? window.i18n.t : (key) => key;
  const lang = window.i18n ? window.i18n.currentLang : 'en';
  
  const total    = allImages.length;
  const versions = allImages.reduce((s, img) => s + Math.max(img.versions.length, 1), 0);
  const avgVersions = total ? (versions / total).toFixed(1) : '0';
  
  // Filter failed count based on current filter
  const filteredFailedCount = currentFilter === 'all' 
    ? failedImages.length 
    : failedImages.filter(i => i.sourceType === currentFilter).length;

  // latest update this week
  const weekAgo = Date.now() - 7 * 86400000;
  const recent  = allImages.filter(img => img.updated && new Date(img.updated) > weekAgo).length;

  // storage size (计算所有版本的总和)
  let totalSizeMB = 0;
  let currentVersionsSizeMB = 0;
  for (const img of allImages) {
    // 累加该镜像所有版本的大小（用于Storage Space）
    if (img.versions && img.versions.length > 0) {
      for (const v of img.versions) {
        totalSizeMB += parseSizeToMB(v.size);
      }
    } else {
      totalSizeMB += parseSizeToMB(img.size);
    }
    // 只计算当前版本大小（用于Avg Image Size）
    currentVersionsSizeMB += parseSizeToMB(img.size);
  }
  const avgSizeMB = allImages.length > 0 ? currentVersionsSizeMB / allImages.length : 0;

  // last synced image
  let lastImg = allImages.reduce((best, img) => {
    if (!img.updated) return best;
    if (!best || new Date(img.updated) > new Date(best.updated)) return img;
    return best;
  }, null);

  const dockerCount  = allImages.filter(i => i.sourceType === 'dockerhub').length;
  const githubCount  = allImages.filter(i => i.sourceType === 'github').length;
  const googleCount  = allImages.filter(i => i.sourceType === 'google').length;
  const redhatCount  = allImages.filter(i => i.sourceType === 'redhat').length;
  const awsCount     = allImages.filter(i => i.sourceType === 'aws').length;

  // Animate numeric stats
  animateStatValue('statTotal', total);
  animateStatValue('statLatestCount', recent || total);
  setText('statAvgVersions', Math.round(parseFloat(avgVersions)));

  // Format size stats
  setText('statStorage', formatSize(totalSizeMB * 1e6));
  setText('statAvg', formatSize(avgSizeMB * 1e6));

  setText('statLastSyncAge', lastImg ? formatAgo(lastImg.updated) : '–');
  setText('statLastSyncName', lastImg ? lastImg.displayName : '–');
  setText('statSub', '+' + total + ' ' + t('stats.thisWeek'));

  // Update failed info in Total Mirrors card
  const failedInfoEl = document.getElementById('statFailedInfo');
  if (failedInfoEl) {
    if (filteredFailedCount > 0) {
      failedInfoEl.textContent = `${filteredFailedCount} ${t('stats.failed')}`;
      failedInfoEl.classList.remove('hidden');
    } else {
      failedInfoEl.classList.add('hidden');
    }
  }

  setText('cnt-all',       allImages.length);
  setText('cnt-dockerhub', dockerCount);
  setText('cnt-github',    githubCount);
  setText('cnt-google',    googleCount);
  setText('cnt-redhat',    redhatCount);
  setText('cnt-aws',       awsCount);
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// ── Card rendering ────────────────────────────
  function buildIcon(sourceType) {
    const icons = {
      dockerhub: `<div class="card-icon icon-docker"><img src="/public/logo/docker.svg" style="width: 20px; height: 20px;" alt="Docker"></div>`,
      github:    `<div class="card-icon icon-github"><img src="/public/logo/GitHub.svg" style="width: 20px; height: 20px;" alt="GitHub"></div>`,
      google:    `<div class="card-icon icon-google"><img src="/public/logo/google.svg" style="width: 20px; height: 20px;" alt="Google"></div>`,
      redhat:    `<div class="card-icon icon-redhat"><img src="/public/logo/redhat.svg" style="width: 20px; height: 20px;" alt="Red Hat"></div>`,
      aws:       `<div class="card-icon icon-aws"><img src="/public/logo/AWS.svg" style="width: 20px; height: 20px;" alt="AWS"></div>`
    };
    return icons[sourceType] || icons.dockerhub;
  }

  function buildVersionSelect(img, ver) {
    const versions = img.versions.length > 1
      ? img.versions.map(v => v.version || v.tag || v)
      : [ver];
    
    // Sanitize ID by replacing special characters that break CSS selectors
    const safeId = img.name.replace(/[^a-zA-Z0-9_-]/g, '__');
    
    const optionsHtml = versions.map(v => {
      const isSelected = v === ver;
      return `<div class="custom-select-option ${isSelected ? 'selected' : ''}" data-value="${v}" onclick="selectVersion('${img.name}', '${v}')">${v}</div>`;
    }).join('');
    
    return `
      <div class="custom-select" id="version-select-${safeId}">
        <div class="custom-select-trigger" onclick="toggleVersionSelect('${img.name}')">
          <span class="mono">${ver}</span>
          <i class="fas fa-chevron-down custom-select-arrow"></i>
        </div>
        <div class="custom-select-options">${optionsHtml}</div>
      </div>`;
  }

  function buildPullCmd(img) {
  // Prefer the target field from the version object if available
  const ver = img.currentVersion;
  const src = img.source || '';

  // Find the version object that matches currentVersion
  const versionObj = img.versions.find(v => (v.version || v.tag || v) === ver);
  if (versionObj && versionObj.target) {
    const target = versionObj.target;
    const colonIdx = target.lastIndexOf(':');
    if (colonIdx > 0) {
      const path = target.substring(0, colonIdx);
      const verFromTarget = target.substring(colonIdx + 1);
      return { path, ver: verFromTarget };
    }
  }

  // Fallback: construct path from source - remove original registry prefix
  let mirrorPath = src;
  if (!src.startsWith('ghcr.io/')) {
    // Remove original registry prefix (docker.io/, gcr.io/, quay.io/, etc.)
    let cleaned = src;
    // Remove version tag from source if present
    const colonIdx = cleaned.lastIndexOf(':');
    if (colonIdx > 0) {
      cleaned = cleaned.substring(0, colonIdx);
    }
    // Remove registry prefix (e.g., docker.io/, gcr.io/, quay.io/, registry.k8s.io/, public.ecr.aws/)
    cleaned = cleaned.replace(/^(docker\.io\/|gcr\.io\/|us\.gcr\.io\/|k8s\.gcr\.io\/|registry\.k8s\.io\/|quay\.io\/|public\.ecr\.aws\/)/, '');
    mirrorPath = `ghcr.io/freemankevin/${cleaned}`;
  }

  return { path: mirrorPath, ver };
}

function buildCard(img, index) {
    const t = window.i18n ? window.i18n.t : (key) => key;
    const { path, ver } = buildPullCmd(img);
    const sourceLabel = getSourceLabel(img.sourceType);
    const ago = formatAgo(img.updated);
    const size = formatSize(img.size);
    const isDark = document.documentElement.classList.contains('dark');

    let iconHtml;
    if (img.sourceType === 'dockerhub') {
      iconHtml = `<div class="w-12 h-12 rounded-xl source-icon-docker border flex items-center justify-center flex-shrink-0"><img src="/public/logo/docker.svg" style="width: 26px; height: 26px;" alt="Docker"></div>`;
    } else if (img.sourceType === 'google') {
      iconHtml = `<div class="w-12 h-12 rounded-xl source-icon-google border flex items-center justify-center flex-shrink-0"><img src="/public/logo/google.svg" style="width: 26px; height: 26px;" alt="Google"></div>`;
    } else if (img.sourceType === 'redhat') {
      iconHtml = `<div class="w-12 h-12 rounded-xl source-icon-redhat border flex items-center justify-center flex-shrink-0"><img src="/public/logo/redhat.svg" style="width: 26px; height: 26px;" alt="Red Hat"></div>`;
    } else if (img.sourceType === 'aws') {
      iconHtml = `<div class="w-12 h-12 rounded-xl source-icon-aws border flex items-center justify-center flex-shrink-0"><img src="/public/logo/AWS.svg" style="width: 26px; height: 26px;" alt="AWS"></div>`;
    } else {
      iconHtml = `<div class="w-12 h-12 rounded-xl source-icon-github border flex items-center justify-center flex-shrink-0"><img src="/public/logo/GitHub.svg" style="width: 26px; height: 26px;" alt="GitHub"></div>`;
    }

    const versionEl = buildVersionSelect(img, ver);

    const officialBadge = img.official
      ? `<span class="badge badge-official">${t('card.official')}</span>`
      : '';

return `
<article class="surface rounded-xl p-5 animate-fade-in" role="listitem" data-name="${img.name}" style="animation-delay:${index * 0.05}s" aria-label="${escHtml(img.displayName)} mirror">
  <div class="flex flex-col lg:flex-row gap-5">
    <div class="flex gap-4 flex-1 min-w-0 items-center">
      ${iconHtml}
      
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2 mb-1.5 flex-wrap">
          <h3 class="text-base font-bold text-primary truncate">${escHtml(img.displayName)}</h3>
          ${officialBadge}
          <span class="tag">${sourceLabel}</span>
        </div>
        
        <p class="text-sm text-secondary mb-3 line-clamp-1">${escHtml(getLocalizedDescription(img))}</p>
        
        <div class="flex items-center gap-3 text-sm text-tertiary mono flex-wrap">
          ${img.stars ? `<button onclick="toggleStar('${img.name}')" class="star-btn flex items-center gap-1.5 hover:text-amber-500 transition-colors" aria-label="Star ${escHtml(img.displayName)}" aria-pressed="false">
            <i class="fas fa-star" style="font-size: 12px;"></i>
            <span style="font-size: 12px;">${img.stars}</span>
          </button>` : ''}
          ${img.layers ? `<span class="flex items-center gap-1.5" style="font-size: 12px;">
            <i class="fas fa-layer-group text-purple-500/60" style="font-size: 12px;"></i>
            ${img.layers} ${t('card.layers')}
          </span>` : ''}
          ${ago ? `<span class="flex items-center gap-1.5" style="font-size: 12px;">
            <i class="far fa-clock text-tertiary/60" style="font-size: 12px;"></i>
            ${ago}
          </span>` : ''}
        </div>
      </div>
    </div>
    
    <div class="flex items-center gap-3 flex-shrink-0">
      ${versionEl}
    </div>
  </div>
  
  <div class="mt-4">
    <div class="terminal-window rounded-xl flex items-center gap-3 group">
      <code class="code-block text-primary truncate flex-1">
        <span class="text-purple-500 select-none" style="font-size: 13px;">$</span>
        <span class="text-blue-500" style="font-size: 13px;">${t('card.dockerPull')} ${escHtml(path)}:${escHtml(ver)}</span>
      </code>
      <button onclick="copyCmd('${img.name}')"
              class="copy-btn flex items-center justify-center"
              aria-label="${t('buttons.copy')}">
        <i id="copy-icon-${img.name}" class="fas fa-copy" style="font-size: 14px;"></i>
      </button>
    </div>
    
    <div class="mt-3 flex items-center justify-between text-sm text-tertiary mono">
      <span class="truncate" style="font-size: 12px;" title="${escHtml(img.source || '')}">${t('card.source')}: ${escHtml(img.source || '')}</span>
      ${size ? `<span class="flex-shrink-0 ml-3" style="font-size: 12px;">${size}</span>` : ''}
    </div>
  </div>
</article>`;
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function buildFailedCard(img, index) {
  const t = window.i18n ? window.i18n.t : (key) => key;
  const lang = window.i18n ? window.i18n.currentLang : 'en';
  const sourceLabel = getSourceLabel(img.sourceType);
  const ago = formatAgo(img.failedAt);

  let iconHtml;
  if (img.sourceType === 'dockerhub') {
    iconHtml = `<div class="w-12 h-12 rounded-xl source-icon-docker border flex items-center justify-center flex-shrink-0 opacity-50"><img src="/public/logo/docker.svg" class="grayscale" style="width: 26px; height: 26px;" alt="Docker"></div>`;
  } else if (img.sourceType === 'google') {
    iconHtml = `<div class="w-12 h-12 rounded-xl source-icon-google border flex items-center justify-center flex-shrink-0 opacity-50"><img src="/public/logo/google.svg" class="grayscale" style="width: 26px; height: 26px;" alt="Google"></div>`;
  } else if (img.sourceType === 'redhat') {
    iconHtml = `<div class="w-12 h-12 rounded-xl source-icon-redhat border flex items-center justify-center flex-shrink-0 opacity-50"><img src="/public/logo/redhat.svg" class="grayscale" style="width: 26px; height: 26px;" alt="Red Hat"></div>`;
  } else if (img.sourceType === 'aws') {
    iconHtml = `<div class="w-12 h-12 rounded-xl source-icon-aws border flex items-center justify-center flex-shrink-0 opacity-50"><img src="/public/logo/AWS.svg" class="grayscale" style="width: 26px; height: 26px;" alt="AWS"></div>`;
  } else {
    iconHtml = `<div class="w-12 h-12 rounded-xl source-icon-github border flex items-center justify-center flex-shrink-0 opacity-50"><img src="/public/logo/GitHub.svg" class="grayscale" style="width: 26px; height: 26px;" alt="GitHub"></div>`;
  }

  const failedText = lang === 'zh' ? t('time.failed') : t('time.failed');

  return `
<article class="surface rounded-xl p-5 animate-fade-in border-2 border-red-500/30 bg-red-500/5" role="listitem" data-name="${img.name}" style="animation-delay:${index * 0.05}s" aria-label="${escHtml(img.displayName)} - ${t('aria.failedLabel')}">
  <div class="flex flex-col lg:flex-row gap-5">
    <div class="flex gap-4 flex-1 min-w-0 items-center">
      ${iconHtml}
      
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2 mb-1.5 flex-wrap">
          <h3 class="text-base font-bold text-gray-400 truncate">${escHtml(img.displayName)}</h3>
          <span class="badge badge-failed">${t('card.syncFailed')}</span>
          <span class="tag">${sourceLabel}</span>
        </div>
        
        <p class="text-sm text-gray-400 mb-3 line-clamp-1">${escHtml(getLocalizedDescription(img))}</p>
        
        <div class="flex items-center gap-3 text-sm text-gray-400 mono flex-wrap">
          ${ago ? `<span class="flex items-center gap-1.5" style="font-size: 12px;">
            <i class="far fa-clock text-gray-400/60" style="font-size: 12px;"></i>
            ${failedText} ${ago}
          </span>` : ''}
          ${img.version ? `<span class="flex items-center gap-1.5" style="font-size: 12px;">
            <i class="fas fa-tag text-gray-400/60" style="font-size: 12px;"></i>
            ${escHtml(img.version)}
          </span>` : ''}
        </div>
      </div>
    </div>
  </div>
  
  <div class="mt-4">
    <div class="terminal-window rounded-xl flex items-center gap-3 group opacity-50">
      <code class="code-block text-gray-400 truncate flex-1">
        <span class="text-gray-400 select-none" style="font-size: 13px;">$</span>
        <span class="text-gray-400" style="font-size: 13px;">${t('card.dockerPull')}</span>
        <span class="text-gray-400" style="font-size: 13px;">${escHtml(img.source || 'N/A')}</span>
      </code>
      <button disabled class="copy-btn flex items-center justify-center opacity-50 cursor-not-allowed" aria-label="${t('card.syncFailed')} - ${t('card.imageNotSynced')}">
        <i class="fas fa-exclamation-triangle text-red-400" style="font-size: 14px;"></i>
      </button>
    </div>
    
    <div class="mt-3 flex items-center justify-between text-sm text-gray-400 mono">
      <span class="truncate" style="font-size: 12px;" title="${escHtml(img.source || '')}">${t('card.source')}: ${escHtml(img.source || 'N/A')}</span>
      <span class="flex-shrink-0 ml-3 text-red-400" style="font-size: 12px;">⚠️ ${t('card.imageNotSynced')}</span>
    </div>
  </div>
</article>`;
}

// ── Custom Version Select ─────────────────────
function toggleVersionSelect(name) {
  // Sanitize ID the same way as in buildVersionSelect
  const safeId = name.replace(/[^a-zA-Z0-9_-]/g, '__');
  const selectEl = document.getElementById(`version-select-${safeId}`);
  if (!selectEl) return;
  
  const isOpen = selectEl.classList.contains('open');
  
  // Close all other selects
  document.querySelectorAll('.custom-select.open').forEach(el => {
    if (el.id !== `version-select-${safeId}`) {
      el.classList.remove('open');
    }
  });
  
  // Toggle current select
  selectEl.classList.toggle('open', !isOpen);
}

function selectVersion(name, tag) {
  const img = imageData[name];
  if (!img) return;
  
  const vObj = img.versions.find(v => (v.version || v.tag || v) === tag);
  img.currentVersion = tag;
  if (vObj && vObj.source) img.source = vObj.source;
  if (vObj && vObj.size) img.size = vObj.size;
  
  // Update allImages entry
  const flat = allImages.find(i => i.name === name);
  if (flat) {
    flat.currentVersion = tag;
    if (vObj && vObj.source) flat.source = vObj.source;
  }
  
  // Close dropdown (use sanitized ID)
  const safeId = name.replace(/[^a-zA-Z0-9_-]/g, '__');
  const selectEl = document.getElementById(`version-select-${safeId}`);
  if (selectEl) selectEl.classList.remove('open');
  
  // Re-render to update display
  render();
}

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
  if (!e.target.closest('.custom-select')) {
    document.querySelectorAll('.custom-select.open').forEach(el => {
      el.classList.remove('open');
    });
  }
  if (!e.target.closest('.pag-size-select')) {
    document.querySelectorAll('.pag-size-select.open').forEach(el => {
      el.classList.remove('open');
    });
  }
});

// ── Version switching ─────────────────────────
function changeVersion(name, tag) {
  const img = imageData[name];
  if (!img) return;

  const vObj = img.versions.find(v => (v.version || v.tag || v) === tag);
  img.currentVersion = tag;
  if (vObj && vObj.source) img.source = vObj.source;
  if (vObj && vObj.size)   img.size   = vObj.size;

  // Also update allImages entry
  const flat = allImages.find(i => i.name === name);
  if (flat) {
    flat.currentVersion = tag;
    if (vObj && vObj.source) flat.source = vObj.source;
  }

  // Patch DOM instead of full re-render
  const { path, ver } = buildPullCmd(img);
  const pathEl = document.getElementById('cmd-path-' + name);
  const verEl  = document.getElementById('cmd-ver-'  + name);
  const srcEl  = document.getElementById('footer-src-' + name);
  if (pathEl) pathEl.textContent = path;
  if (verEl)  verEl.textContent  = ver;
  if (srcEl)  srcEl.textContent  = 'Source: ' + (img.source || '');
}

// ── Copy ──────────────────────────────────────
function copyCmd(name) {
  const img = imageData[name] || allImages.find(i => i.name === name);
  if (!img) return;

  const { path, ver } = buildPullCmd(img);
  const cmd = `docker pull ${path}:${ver}`;

  const btn = document.querySelector(`button[onclick="copyCmd('${name}')"]`);
  const iconEl = document.getElementById('copy-icon-' + name);

  const doFlash = () => flash(iconEl, btn);

  if (navigator.clipboard) {
    navigator.clipboard.writeText(cmd).then(doFlash).catch(doFlash);
  } else {
    const ta = document.createElement('textarea');
    ta.value = cmd; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); document.body.removeChild(ta);
    doFlash();
  }
}

function flash(iconEl, btnEl) {
  if (!iconEl || !btnEl) return;
  
  // Add copied state
  iconEl.className = 'fas fa-check';
  btnEl.classList.add('copied');
  
  // Add bounce animation to icon
  iconEl.style.animation = 'copySuccess 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)';
  
  // Remove states after animation
  setTimeout(() => {
    iconEl.className = 'fas fa-copy';
    iconEl.style.animation = '';
    btnEl.classList.remove('copied');
  }, 2000);
}

// ── Star toggle ──────────────────────────────
function toggleStar(name) {
  const t = window.i18n ? window.i18n.t : (key) => key;
  const btn = document.querySelector(`button[onclick="toggleStar('${name}')"]`);
  if (!btn) return;
  const isStarred = btn.getAttribute('aria-pressed') === 'true';
  btn.setAttribute('aria-pressed', !isStarred);
  const icon = btn.querySelector('i');
  if (icon) {
    if (!isStarred) {
      icon.className = 'fas fa-star text-amber-500';
      const countSpan = btn.querySelector('span');
      if (countSpan) {
        const count = parseInt(countSpan.textContent) || 0;
        countSpan.textContent = count + 1;
      }
      showToast(t('toast.addedToFavorites'));
    } else {
      icon.className = 'fas fa-star';
      const countSpan = btn.querySelector('span');
      if (countSpan) {
        const count = parseInt(countSpan.textContent) || 1;
        countSpan.textContent = Math.max(0, count - 1);
      }
      showToast(t('toast.removedFromFavorites'));
    }
  }
}

// ── Toast ─────────────────────────────────────
function showToast(msg, type = 'green') {
  const wrap = document.getElementById('toastWrap');
  const t = document.createElement('div');
  
  // Enhanced toast with better styling
  t.className = `toast ${type}`;
  t.innerHTML = `
    <div class="flex items-center gap-3">
      <div class="toast-icon w-6 h-6 rounded-full flex items-center justify-center">
        <i class="fas fa-check text-sm"></i>
      </div>
      <span class="font-medium">${msg}</span>
    </div>
  `;
  
  wrap.appendChild(t);
  
  // Animate in
  requestAnimationFrame(() => { 
    requestAnimationFrame(() => { 
      t.classList.add('show'); 
    }); 
  });
  
  // Auto remove
  setTimeout(() => {
    t.classList.remove('show');
    setTimeout(() => t.remove(), 400);
  }, 3000);
}

// ── Pagination ────────────────────────────────
function changePageSize(size) {
  itemsPerPage = parseInt(size);
  localStorage.setItem('itemsPerPage', itemsPerPage);
  currentPage = 1;
  render();
}

function togglePageSizeSelect() {
  const selectEl = document.getElementById('pag-size-select');
  if (!selectEl) return;
  
  // Close all other selects first
  document.querySelectorAll('.pag-size-select.open').forEach(el => {
    if (el.id !== 'pag-size-select') {
      el.classList.remove('open');
    }
  });
  
  selectEl.classList.toggle('open');
}

function selectPageSize(size) {
  itemsPerPage = parseInt(size);
  localStorage.setItem('itemsPerPage', itemsPerPage);
  currentPage = 1;
  
  // Close dropdown
  const selectEl = document.getElementById('pag-size-select');
  if (selectEl) selectEl.classList.remove('open');
  
  render();
}

function buildPagination(total, filtered) {
  const t = window.i18n ? window.i18n.t : (key) => key;
  const totalPages = Math.ceil(filtered / itemsPerPage);
  const container  = document.getElementById('pagination');
  if (!container) return;

  if (filtered === 0) { container.innerHTML = ''; return; }

  const from = (currentPage - 1) * itemsPerPage + 1;
  const to   = Math.min(currentPage * itemsPerPage, filtered);

  const pages = [];
  const maxVisible = 5;
  let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
  let endPage = Math.min(totalPages, startPage + maxVisible - 1);
  
  if (endPage - startPage + 1 < maxVisible) {
    startPage = Math.max(1, endPage - maxVisible + 1);
  }

  for (let p = startPage; p <= endPage; p++) {
    pages.push(p);
  }

  const btns = pages.map(p => {
    return `<button class="pag-btn num ${p === currentPage ? 'active' : ''}" onclick="goToPage(${p})">${p}</button>`;
  }).join('');

  const sizeOptions = [10, 20, 50, 100].map(size => 
    `<div class="pag-size-option ${size === itemsPerPage ? 'selected' : ''}" onclick="selectPageSize(${size})">${size}</div>`
  ).join('');

  container.innerHTML = `
    <div class="pag-wrap">
      <span class="pag-info">${t('pagination.showing')} ${from}–${to} ${t('pagination.of')} ${filtered}</span>
      <div class="pag-controls">
        <div class="pag-size-select" id="pag-size-select">
          <div class="pag-size-trigger" onclick="togglePageSizeSelect()">
            <span>${itemsPerPage}</span>
            <i class="fas fa-chevron-down" style="font-size: 10px; transition: transform 0.2s ease;"></i>
          </div>
          <div class="pag-size-options">${sizeOptions}</div>
        </div>
        <div class="pag-btns">
          <button class="pag-btn nav" onclick="goToPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>
            <i class="fas fa-chevron-left" style="font-size: 12px;"></i>
          </button>
          ${btns}
          <button class="pag-btn nav" onclick="goToPage(${currentPage + 1})" ${currentPage === totalPages || totalPages === 0 ? 'disabled' : ''}>
            <i class="fas fa-chevron-right" style="font-size: 12px;"></i>
          </button>
        </div>
      </div>
    </div>`;
}

function goToPage(p) {
  const filtered = getFiltered();
  const totalPages = Math.ceil(filtered.length / itemsPerPage);
  if (p < 1 || p > totalPages) return;
  currentPage = p;
  renderList(filtered);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Render ────────────────────────────────────
function renderList(filtered) {
  const list     = document.getElementById('mirrorList');
  const failedList = document.getElementById('failedMirrorList');
  const empty    = document.getElementById('emptyState');
  const pagEl    = document.getElementById('pagination');
  const failedSection = document.getElementById('failedSection');

  // Filter failed images by current source type
  const filteredFailed = failedImages.filter(img => {
    if (currentFilter === 'all') return true;
    return img.sourceType === currentFilter;
  });

  // Render failed images section if there are failed images matching the filter
  if (filteredFailed.length > 0 && failedList && failedSection) {
    failedSection.classList.remove('hidden');
    failedList.innerHTML = filteredFailed.map((img, i) => buildFailedCard(img, i)).join('');
    
    // Update failed count in section header
    const failedCountEl = document.getElementById('failedSectionCount');
    if (failedCountEl) {
      failedCountEl.textContent = filteredFailed.length;
    }
  } else if (failedSection) {
    failedSection.classList.add('hidden');
  }

  // Render successful images
  if (!filtered.length) {
    list.innerHTML  = '';
    pagEl.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }

  empty.classList.add('hidden');

  const start = (currentPage - 1) * itemsPerPage;
  const page  = filtered.slice(start, start + itemsPerPage);

  list.innerHTML = page.map((img, i) => buildCard(img, i)).join('');

  buildPagination(allImages.length, filtered.length);
}

function render() {
  updateStats();
  const filtered = getFiltered();
  renderList(filtered);
}

// ── Sample data (used when images.json not found) ──
function sampleData() {
  return [
    {
      name: 'library/elasticsearch',
      description: 'Elasticsearch search and analytics engine',
      stars: 124, layers: 12,
      updated: new Date(Date.now() - 4 * 86400000).toISOString(),
      platforms: ['AMD64','ARM64'],
      source: 'docker.io/library/elasticsearch',
      size: '1.2 GB',
      versions: [
        { tag: '9.3.0', source: 'docker.io/library/elasticsearch', size: '1.2 GB' },
        { tag: '8.17.0', source: 'docker.io/library/elasticsearch', size: '1.1 GB' },
      ],
    },
    {
      name: 'minio/minio',
      description: 'MinIO high-performance object storage',
      stars: 89, layers: 8,
      updated: new Date(Date.now() - 19 * 86400000).toISOString(),
      platforms: ['AMD64','ARM64'],
      source: 'docker.io/minio/minio',
      size: '284 MB',
      versions: [
        { tag: 'RELEASE.2025-10-15', source: 'docker.io/minio/minio', size: '284 MB' },
        { tag: 'RELEASE.2025-09-01', source: 'docker.io/minio/minio', size: '280 MB' },
      ],
    },
    {
      name: 'library/redis',
      description: 'Redis in-memory data structure store',
      stars: 210, layers: 6,
      updated: new Date(Date.now() - 1 * 86400000).toISOString(),
      platforms: ['AMD64','ARM64'],
      source: 'docker.io/library/redis',
      size: '138 MB',
      versions: [
        { tag: '7.4', source: 'docker.io/library/redis', size: '138 MB' },
        { tag: '7.2', source: 'docker.io/library/redis', size: '130 MB' },
      ],
    },
    {
      name: 'library/nginx',
      description: 'Official build of Nginx web server',
      stars: 305, layers: 7,
      updated: new Date(Date.now() - 3 * 86400000).toISOString(),
      platforms: ['AMD64','ARM64'],
      source: 'docker.io/library/nginx',
      size: '67 MB',
      versions: [
        { tag: '1.27', source: 'docker.io/library/nginx', size: '67 MB' },
        { tag: '1.26', source: 'docker.io/library/nginx', size: '65 MB' },
      ],
    },
    {
      name: 'google-containers/pause',
      description: 'The pause container image — Google Container Registry',
      stars: 0, layers: 2,
      updated: new Date(Date.now() - 60 * 86400000).toISOString(),
      platforms: ['AMD64','ARM64'],
      source: 'gcr.io/google-containers/pause',
      size: '750 KB',
      versions: [
        { tag: '3.9', source: 'gcr.io/google-containers/pause', size: '750 KB' },
        { tag: '3.8', source: 'gcr.io/google-containers/pause', size: '720 KB' },
      ],
    },
    {
      name: 'ubi8/ubi',
      description: 'Red Hat Universal Base Image 8',
      stars: 0, layers: 4,
      updated: new Date(Date.now() - 14 * 86400000).toISOString(),
      platforms: ['AMD64','ARM64'],
      source: 'quay.io/ubi8/ubi',
      size: '215 MB',
      versions: [
        { tag: '8.10', source: 'quay.io/ubi8/ubi', size: '215 MB' },
        { tag: '8.9',  source: 'quay.io/ubi8/ubi', size: '210 MB' },
      ],
    },
  ];
}



// ── Back to Top ───────────────────────────────
function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function initBackToTop() {
  const btn = document.getElementById('backToTop');
  if (!btn) return;
  
  const threshold = 300;
  
  window.addEventListener('scroll', () => {
    if (window.scrollY > threshold) {
      btn.classList.add('visible');
      btn.classList.remove('hidden');
    } else {
      btn.classList.remove('visible');
      btn.classList.add('hidden');
    }
  }, { passive: true });
}

// ── Full Page Background Carousel ───────────────────────────────
function initPageBackground() {
  const bgImages = [
    '/public/background/wallhaven-j5g3zy.jpg',
    '/public/background/wallhaven-135j73.jpg'
  ];

  const pageBg = document.getElementById('pageBg');
  if (!pageBg) return;

  const totalBgs = bgImages.length;
  let currentBg = 0;

  function showBg(index) {
    currentBg = index;
    pageBg.style.backgroundImage = `url('${bgImages[index]}')`;
  }

  function nextBg() {
    currentBg = (currentBg + 1) % totalBgs;
    showBg(currentBg);
  }

  // Random background on page refresh
  const randomIndex = Math.floor(Math.random() * totalBgs);
  showBg(randomIndex);

  // Auto-rotate every 30 minutes
  setInterval(nextBg, 30 * 60 * 1000);
}

// ── Boot ──────────────────────────────────────
initTheme();
initPageBackground();
loadImages();
initBackToTop();
