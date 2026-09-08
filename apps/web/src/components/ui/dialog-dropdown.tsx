"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

const DIALOG_CONTENT_SELECTOR = '[data-slot="dialog-content"]';

interface DropdownRect {
    top: number;
    left: number;
    width: number;
}

function measureInContent(
    anchor: HTMLElement,
    content: HTMLElement,
): DropdownRect | null {
    const a = anchor.getBoundingClientRect();
    const c = content.getBoundingClientRect();
    const style = getComputedStyle(content);
    const borderTop = parseFloat(style.borderTopWidth) || 0;
    const borderLeft = parseFloat(style.borderLeftWidth) || 0;
    const top = a.bottom - (c.top + borderTop);
    const left = a.left - (c.left + borderLeft);
    return { top, left, width: a.width };
}

function useDialogDropdown(open: boolean) {
    const anchorRef = useRef<HTMLElement | null>(null);
    const popoverRef = useRef<HTMLDivElement | null>(null);
    const [rect, setRect] = useState<DropdownRect | null>(null);
    const [content, setContent] = useState<HTMLElement | null>(null);

    useEffect(() => {
        if (!open) {
            setRect(null);
            return;
        }
        const el = document.querySelector<HTMLElement>(DIALOG_CONTENT_SELECTOR);
        setContent(el);
        const measure = () => {
            const anchor = anchorRef.current;
            if (!anchor) {
                setRect(null);
                return;
            }
            setRect(el ? measureInContent(anchor, el) : null);
        };
        measure();
        window.addEventListener("resize", measure);
        window.addEventListener("scroll", measure, true);
        return () => {
            window.removeEventListener("resize", measure);
            window.removeEventListener("scroll", measure, true);
        };
    }, [open]);

    const render = useMemo(
        () =>
            // eslint-disable-next-line react/display-name
            (children: ReactNode, className?: string): ReactNode => {
                if (children == null) return null;
                if (content && rect) {
                    return createPortal(
                        <div
                            ref={popoverRef}
                            className={cn("absolute z-50", className)}
                            style={{
                                top: `${rect.top + 4}px`,
                                left: `${rect.left}px`,
                                width: `${rect.width}px`,
                            }}
                        >
                            {children}
                        </div>,
                        content,
                    );
                }
                return (
                    <div
                        ref={popoverRef}
                        className={cn(
                            "absolute left-0 top-[calc(100%+4px)] z-50 w-full",
                            className,
                        )}
                    >
                        {children}
                    </div>
                );
            },
        [content, rect],
    );

    return { anchorRef, popoverRef, render };
}

export { useDialogDropdown };
