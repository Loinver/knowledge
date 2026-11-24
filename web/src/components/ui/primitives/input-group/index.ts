// Source: https://www.shadcn-vue.com/r/styles/reka-nova/input-group.json; original registry SHA256: 128d4c1d4a279152f73826699d795b0faa34d308851c92a39b739a5504ebc3e5. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md.
import type { VariantProps } from 'class-variance-authority'
import { cva } from 'class-variance-authority'
import type { HTMLAttributes } from 'vue'

import type { ButtonVariants } from '@/components/ui/primitives/button'

export { default as InputGroup } from './InputGroup.vue'
export { default as InputGroupAddon } from './InputGroupAddon.vue'
export { default as InputGroupButton } from './InputGroupButton.vue'
export { default as InputGroupInput } from './InputGroupInput.vue'
export { default as InputGroupText } from './InputGroupText.vue'
export { default as InputGroupTextarea } from './InputGroupTextarea.vue'

export const inputGroupAddonVariants = cva(
  'text-muted-foreground h-auto gap-2 py-1.5 text-[length:var(--font-body)] font-medium group-data-[disabled=true]/input-group:opacity-50 [&>kbd]:rounded-[var(--radius-control)] [&>svg:not([class*=size-])]:size-[var(--space-4)] flex cursor-text items-center justify-center select-none',
  {
    variants: {
      align: {
        'inline-start': 'pl-2 has-[>button]:ml-[-0.3rem] has-[>kbd]:ml-[-0.15rem] order-first',
        'inline-end': 'pr-2 has-[>button]:mr-[-0.3rem] has-[>kbd]:mr-[-0.15rem] order-last',
        'block-start':
          'px-2.5 pt-2 group-has-[>input]/input-group:pt-2 [.border-b]:pb-2 order-first w-full justify-start',
        'block-end':
          'px-2.5 pb-2 group-has-[>input]/input-group:pb-2 [.border-t]:pt-2 order-last w-full justify-start',
      },
    },
    defaultVariants: {
      align: 'inline-start',
    },
  },
)

export type InputGroupVariants = VariantProps<typeof inputGroupAddonVariants>

export const inputGroupButtonVariants = cva(
  'gap-2 text-[length:var(--font-body)] flex items-center shadow-none',
  {
    variants: {
      size: {
        xs: 'h-[var(--space-5)] gap-1 rounded-[var(--radius-control)] px-1.5 [&>svg:not([class*=size-])]:size-[calc(var(--space-1)*3.5)]',
        sm: '',
        'icon-xs': 'size-[var(--space-5)] rounded-[var(--radius-control)] p-0 has-[>svg]:p-0',
        'icon-sm': 'size-[var(--space-6)] p-0 has-[>svg]:p-0',
      },
    },
    defaultVariants: {
      size: 'xs',
    },
  },
)

export type InputGroupButtonVariants = VariantProps<typeof inputGroupButtonVariants>

export interface InputGroupButtonProps {
  variant?: ButtonVariants['variant']
  size?: InputGroupButtonVariants['size']
  class?: HTMLAttributes['class']
}
