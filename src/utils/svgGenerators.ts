/**
 * Fernwood Visual Generator Utility
 * Generates custom, crisp, styled SVG poster graphics for mock campaign imagery
 * based on brand colors, tone/mood tags, and prompt parameters.
 */

interface ImageGenOptions {
  brandName: string;
  tagline: string;
  tone: string;
  primaryColor: string;
  secondaryColor: string;
  accentColor: string;
  attemptNumber: number;
  isWarmTone?: boolean;
}

export function generateCampaignSVG(options: ImageGenOptions): string {
  const {
    brandName,
    tagline,
    tone,
    primaryColor = '#1E3A2B',
    secondaryColor = '#F4F1EA',
    accentColor = '#D97706',
    attemptNumber = 1
  } = options;

  // Render variations based on attempt number to visually show prompt refinements!
  const isRefined = attemptNumber > 1;

  // Determine abstract visual elements based on tone
  let patternElements = '';
  if (tone.includes('Organic') || tone.includes('Earthy') || tone.includes('Cozy')) {
    patternElements = `
      <circle cx="600" cy="200" r="280" fill="${accentColor}" opacity="${isRefined ? '0.25' : '0.12'}" />
      <path d="M 100,500 Q 300,200 600,450 T 1100,300" fill="none" stroke="${accentColor}" stroke-width="${isRefined ? '6' : '3'}" opacity="0.4" />
      <path d="M 0,700 Q 400,500 800,650 T 1200,600 L 1200,800 L 0,800 Z" fill="${secondaryColor}" opacity="0.15" />
      <circle cx="200" cy="300" r="8" fill="${accentColor}" opacity="0.6" />
      <circle cx="240" cy="260" r="14" fill="${accentColor}" opacity="0.4" />
    `;
  } else if (tone.includes('Futuristic') || tone.includes('High-Tech')) {
    patternElements = `
      <rect x="700" y="100" width="350" height="350" rx="24" fill="none" stroke="${accentColor}" stroke-width="2" opacity="0.3" transform="rotate(15 875 275)" />
      <path d="M0 0 L1200 800 M1200 0 L0 800" stroke="${secondaryColor}" stroke-width="1" opacity="0.1" />
      <circle cx="875" cy="275" r="120" fill="none" stroke="${accentColor}" stroke-width="4" opacity="0.6" stroke-dasharray="10 15" />
    `;
  } else if (tone.includes('Bold') || tone.includes('Playful') || tone.includes('Athletic')) {
    patternElements = `
      <polygon points="600,100 1100,400 800,800 200,700" fill="${accentColor}" opacity="${isRefined ? '0.22' : '0.1'}" />
      <circle cx="900" cy="250" r="180" fill="${secondaryColor}" opacity="0.15" />
      <line x1="100" y1="100" x2="500" y2="700" stroke="${accentColor}" stroke-width="12" opacity="0.5" stroke-linecap="round" />
    `;
  } else {
    // Minimalist Luxury
    patternElements = `
      <rect x="150" y="120" width="900" height="560" fill="none" stroke="${accentColor}" stroke-width="1" opacity="0.4" />
      <circle cx="600" cy="400" r="220" fill="none" stroke="${secondaryColor}" stroke-width="1" opacity="0.25" />
      <line x1="600" y1="180" x2="600" y2="620" stroke="${accentColor}" stroke-width="1" opacity="0.3" />
    `;
  }

  const svg = `
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800" width="100%" height="100%">
    <defs>
      <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="${primaryColor}" />
        <stop offset="100%" stop-color="${adjustHexColor(primaryColor, -40)}" />
      </linearGradient>
      <linearGradient id="accentGrad" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="${accentColor}" />
        <stop offset="100%" stop-color="${secondaryColor}" />
      </linearGradient>
      <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
        <feDropShadow dx="0" dy="12" stdDeviation="16" flood-color="#000000" flood-opacity="0.35"/>
      </filter>
    </defs>

    <!-- Background -->
    <rect width="1200" height="800" fill="url(#bgGrad)" />

    <!-- Decorative Patterns -->
    ${patternElements}

    <!-- Quality Tag Badge -->
    <g transform="translate(80, 80)">
      <rect width="180" height="36" rx="18" fill="${secondaryColor}" opacity="0.15" />
      <rect width="180" height="36" rx="18" fill="none" stroke="${secondaryColor}" stroke-width="1" opacity="0.3" />
      <text x="24" y="23" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="13" font-weight="600" fill="${secondaryColor}" letter-spacing="1">
        ${tone.toUpperCase()}
      </text>
    </g>

    ${isRefined ? `
    <g transform="translate(280, 80)">
      <rect width="160" height="36" rx="18" fill="${accentColor}" opacity="0.9" />
      <text x="20" y="23" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="12" font-weight="700" fill="#FFFFFF" letter-spacing="0.5">
        ✦ RETRY V${attemptNumber} PASSED
      </text>
    </g>
    ` : ''}

    <!-- Central Brand Content Box -->
    <g transform="translate(80, 360)">
      <text x="0" y="0" font-family="Georgia, serif" font-size="64" font-weight="700" fill="${secondaryColor}" filter="url(#shadow)">
        ${escapeXml(brandName)}
      </text>
      
      <!-- Accent Line -->
      <rect x="0" y="24" width="${isRefined ? '180' : '100'}" height="4" rx="2" fill="url(#accentGrad)" />
      
      <text x="0" y="70" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="24" font-weight="400" fill="${secondaryColor}" opacity="0.9">
        "${escapeXml(tagline)}"
      </text>
    </g>

    <!-- Footer Provenance Badge -->
    <g transform="translate(80, 720)">
      <text x="0" y="0" font-family="monospace" font-size="12" fill="${secondaryColor}" opacity="0.5">
        FERNWOOD GENBLAZE IMAGE PIPELINE • MODEL: genblaze-image-v3 • ATTEMPT #${attemptNumber}
      </text>
    </g>
  </svg>
  `.trim();

  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function adjustHexColor(hex: string, percent: number): string {
  let num = parseInt(hex.replace('#', ''), 16);
  if (isNaN(num)) return hex;
  let amt = Math.round(2.55 * percent);
  let R = (num >> 16) + amt;
  let G = (num >> 8 & 0x00FF) + amt;
  let B = (num & 0x0000FF) + amt;
  return '#' + (0x1000000 + (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 + (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 + (B < 255 ? B < 1 ? 0 : B : 255)).toString(16).slice(1);
}

function escapeXml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}
