import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "cn";

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-[.68rem] border bg-clip-padding text-sm font-extrabold whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-55 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "border-[#166534] bg-[#15803d] text-white shadow-[0_7px_14px_rgb(21_128_61_/_17%)] hover:-translate-y-px hover:bg-[#166534] hover:text-white hover:shadow-[0_10px_18px_rgb(22_101_52_/_24%)]",
        outline:
          "border-[#cbd5e1] bg-white text-[#334155] shadow-none hover:bg-[#f8fafc] hover:text-[#172554] dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        secondary:
          "border-[#cbd5e1] bg-white text-[#334155] shadow-none hover:bg-[#f8fafc] hover:text-[#172554] dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        ghost:
          "border-transparent bg-transparent text-[#526179] shadow-none hover:bg-[#f1f5f9] hover:text-[#1e293b] dark:hover:bg-[#213329] dark:hover:text-[#f1f8f3]",
        destructive:
          "border-[#be123c] bg-[#be123c] text-white shadow-[0_7px_14px_rgb(190_18_60_/_17%)] hover:-translate-y-px hover:bg-[#9f1239] hover:text-white hover:shadow-[0_10px_18px_rgb(190_18_60_/_24%)]",
        link: "border-transparent bg-transparent text-[#15803d] shadow-none hover:text-[#166534] hover:underline",
      },
      size: {
        default:
          "min-h-[2.65rem] gap-1.5 px-[.95rem] py-[.65rem] has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        icon: "size-8",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
