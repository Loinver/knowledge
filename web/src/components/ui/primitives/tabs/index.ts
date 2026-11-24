// Source: https://www.shadcn-vue.com/r/styles/reka-nova/tabs.json; original registry SHA256: f2c275bc4026050f6d5b447a38a2e3802e55d8adfd27c172c73401339cb7b25f. Copyright (c) 2023 unovue; MIT. See ../../THIRD_PARTY_LICENSES.md.
import type { VariantProps } from 'class-variance-authority'
import { cva } from 'class-variance-authority'

export { default as Tabs } from './Tabs.vue'
export { default as TabsContent } from './TabsContent.vue'
export { default as TabsList } from './TabsList.vue'
export { default as TabsTrigger } from './TabsTrigger.vue'

export const tabsListVariants = cva(
  'rounded-[var(--radius-control)] p-0.75 group-data-horizontal/tabs:h-[var(--control-height)] data-[variant=line]:rounded-none group/tabs-list inline-flex w-fit items-center justify-center text-muted-foreground group-data-vertical/tabs:h-fit group-data-vertical/tabs:flex-col',
  {
    variants: {
      variant: {
        default: 'bg-muted',
        line: 'gap-1 bg-transparent',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
)

export type TabsListVariants = VariantProps<typeof tabsListVariants>
