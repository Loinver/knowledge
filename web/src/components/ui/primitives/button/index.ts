// Source: https://www.shadcn-vue.com/r/styles/reka-nova/button.json; original registry SHA256: 669f536a5d4cd520e5e0d0263e0e9f35064751b2c07358e48379d575ceb8d174. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md.
import type { VariantProps } from 'class-variance-authority'
import { cva } from 'class-variance-authority'

export { default as Button } from './Button.vue'

export const buttonVariants = cva(
  'focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive dark:aria-invalid:border-destructive/50 rounded-[var(--radius-control)] border border-transparent bg-clip-padding text-[length:var(--font-body)] font-medium focus-visible:ring-3 aria-invalid:ring-3 active:not-aria-[haspopup]:translate-y-px [&_svg:not([class*=size-])]:size-[var(--space-4)] group/button inline-flex shrink-0 items-center justify-center whitespace-nowrap transition-all outline-none select-none disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground [a]:hover:bg-primary/80',
        outline:
          'border-border bg-background hover:bg-muted hover:text-foreground dark:bg-input/30 dark:border-input dark:hover:bg-input/50 aria-expanded:bg-muted aria-expanded:text-foreground',
        secondary:
          'bg-secondary text-secondary-foreground hover:bg-secondary/80 aria-expanded:bg-secondary aria-expanded:text-secondary-foreground',
        ghost:
          'hover:bg-muted hover:text-foreground dark:hover:bg-muted/50 aria-expanded:bg-muted aria-expanded:text-foreground',
        destructive:
          'bg-destructive/10 hover:bg-destructive/20 focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40 dark:bg-destructive/20 text-destructive focus-visible:border-destructive/40 dark:hover:bg-destructive/30',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        default:
          'h-[var(--control-height)] gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2',
        xs: 'h-[var(--control-height-small)] gap-1 rounded-[var(--radius-control)] px-2 text-[length:var(--font-caption)] in-data-[slot=button-group]:rounded-[var(--radius-control)] has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*=size-])]:size-[var(--space-3)]',
        sm: 'h-[var(--control-height-small)] gap-1 rounded-[var(--radius-control)] px-2.5 text-[length:var(--font-small)] in-data-[slot=button-group]:rounded-[var(--radius-control)] has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*=size-])]:size-[calc(var(--space-1)*3.5)]',
        lg: 'h-[var(--control-height-large)] gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2',
        icon: 'size-[var(--control-height)]',
        'icon-xs':
          'size-[var(--control-height-small)] rounded-[var(--radius-control)] in-data-[slot=button-group]:rounded-[var(--radius-control)] [&_svg:not([class*=size-])]:size-[var(--space-3)]',
        'icon-sm':
          'size-[var(--control-height-small)] rounded-[var(--radius-control)] in-data-[slot=button-group]:rounded-[var(--radius-control)]',
        'icon-lg': 'size-[var(--control-height-large)]',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)
export type ButtonVariants = VariantProps<typeof buttonVariants>
