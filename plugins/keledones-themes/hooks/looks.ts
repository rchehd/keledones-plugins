import type { makeColors } from './make-colors.js'

type Palette = Parameters<typeof makeColors>[0]

export type Look = { palette: Palette; scene?: string }

// Warm cream by day, deep blue-green by night, with the gold of the Keledones bird.
const KELEDONES: Palette = {
  label: 'Keledones',
  roles: { accent: '#1F5673', danger: '#B3423A', success: '#2F7D5B', warning: '#D99A43', pro: '#7A5C9E' },
  light: {
    gray: {
      anchors: {
        'surface-0': '#EFEBE1',
        'surface-1': '#F4F0E6',
        'surface-2': '#FBF9F3',
        'surface-3': '#FBF9F3',
        'text-primary': '#071218',
        'text-secondary': '#364249',
        'text-muted': '#575450',
      },
    },
    git: { added: '#2F7D5B', removed: '#B3423A', modified: '#1F5673', merged: '#7A5C9E', conflicting: '#B3423A', closed: '#575450', draft: '#575450' },
  },
  dark: {
    roles: { accent: '#9CCBDD' },
    gray: {
      anchors: {
        'surface-0': '#102633',
        'surface-1': '#14303F',
        'surface-2': '#173545',
        'surface-3': '#173545',
        'text-primary': '#F4F0E6',
        'text-secondary': '#D3DDE0',
        'text-muted': '#A9BBC2',
      },
    },
    git: { added: '#6FBF95', removed: '#E58A7F', modified: '#9CCBDD', merged: '#B9A0DA', conflicting: '#E58A7F', closed: '#A9BBC2', draft: '#A9BBC2' },
  },
}

// Graphite gray surfaces and a blue accent, in the manner of a modern dark IDE.
const GRAPHITE: Palette = {
  label: 'Graphite',
  roles: { accent: '#3574F0', danger: '#F75464', success: '#6AAB73', warning: '#F2C55C', pro: '#C77DBB' },
  dark: {
    gray: {
      anchors: {
        'surface-0': '#1E1F22',
        'surface-1': '#26282B',
        'surface-2': '#2B2D30',
        'surface-3': '#2B2D30',
        'text-primary': '#DFE1E5',
        'text-secondary': '#BCBEC4',
        'text-muted': '#9A9EA6',
      },
    },
    git: { added: '#6AAB73', removed: '#F75464', modified: '#56A8F5', merged: '#C77DBB', conflicting: '#E06C75', closed: '#9A9EA6', draft: '#9A9EA6' },
  },
  light: {
    gray: {
      anchors: {
        'surface-0': '#F2F3F5',
        'surface-1': '#F7F8FA',
        'surface-2': '#FFFFFF',
        'surface-3': '#FFFFFF',
        'text-primary': '#080808',
        'text-secondary': '#494B57',
        'text-muted': '#6C707E',
      },
    },
    git: { added: '#208A3C', removed: '#DB3B4B', modified: '#3574F0', merged: '#8C4FBC', conflicting: '#C7222D', closed: '#6C707E', draft: '#6C707E' },
  },
}

export const BIRD = 'keledones-bird'
export const LOOKS: Record<string, Look> = { keledones: { palette: KELEDONES, scene: BIRD }, graphite: { palette: GRAPHITE } }
export const DEFAULT_LOOK = 'keledones'
