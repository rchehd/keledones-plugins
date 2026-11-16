import type { EngineInterface, Register } from 'claude-code'

import { makeColors } from './make-colors.js'
import { BIRD, DEFAULT_LOOK, LOOKS } from './looks.js'
import { BIRD_SCENE } from './scene.js'

const COMMAND = 'look'
const OFF = 'off'
const NAMES = Object.keys(LOOKS)

async function current($: EngineInterface): Promise<string> {
  const stored = await $.store.get('look')

  return typeof stored === 'string' && (stored === OFF || stored in LOOKS) ? stored : DEFAULT_LOOK
}

async function apply($: EngineInterface, name: string): Promise<string> {
  const look = LOOKS[name]

  if (look === undefined) {
    return `Unknown look ${name}; choose ${NAMES.join(', ')} or ${OFF}.`
  }
  const { palette, scene } = look
  const { theme, problems } = makeColors(palette)
  const unpainted = problems.find(line => line.startsWith("Desktop won't paint"))

  if (unpainted !== undefined) {
    return unpainted
  }
  const set = await $.theme.set(scene === undefined ? { colors: theme } : { colors: theme, backdrop: { scene } })

  return set.isDrawn ? `${palette.label} look is on.` : `${palette.label} look is on; ${set.reason}`
}

export const register: Register = on => {
  on('ui.render', { component: 'Backdrop' }, ($, e, next) => {
    if (e.props.scene !== BIRD || (e.surface !== 'desktop' && e.surface !== 'mobile')) {
      return next(e)
    }
    const { Svg } = $.ui.resolve(e)

    return <Svg source={BIRD_SCENE} alt="A faint Keledones bird watermark behind the conversation" />
  })

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: COMMAND,
      description: `Switch the Claude app look: /look ${NAMES.join(' | ')} | ${OFF}`,
    })
    const name = await current($)

    if (name !== OFF) {
      await apply($, name)
    }

    return next(e)
  })

  on('command.run', { command: COMMAND }, async ($, e) => {
    const choice = e.args.trim().toLowerCase()

    if (choice === OFF) {
      await $.store.set('look', OFF)
      await $.theme.clear()

      return { text: 'The default look is back. Choose another with /look keledones or /look graphite.' }
    }

    if (choice in LOOKS) {
      await $.store.set('look', choice)

      return { text: await apply($, choice) }
    }

    if (choice !== '') {
      return { text: `Unknown look "${choice}". Available: ${NAMES.join(', ')}, ${OFF}.` }
    }

    return { text: `Current look: ${await current($)}. Available: ${NAMES.join(', ')}, ${OFF}.` }
  })
}
