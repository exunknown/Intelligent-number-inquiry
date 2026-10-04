import { Gauge, UserRound } from "lucide-react";
import {
    forwardRef,
    useEffect,
    useImperativeHandle,
    useRef,
    useState,
    type KeyboardEvent,
} from "react";
import { nextFocusableIndex } from "../lib/userManagement";

export type UserAvatarMenuHandle = {
    focusTrigger: () => void;
};

type UserAvatarMenuProps = {
    username: string;
    showManagement: boolean;
    onOpenManagement: () => void;
    showGovernance: boolean;
    onOpenGovernance: () => void;
    onLogout: () => void;
    menuPlacement?: "above" | "below";
    className?: string;
};

export const UserAvatarMenu = forwardRef<UserAvatarMenuHandle, UserAvatarMenuProps>(
    function UserAvatarMenu(
        {
            username,
            showManagement,
            onOpenManagement,
            showGovernance,
            onOpenGovernance,
            onLogout,
            menuPlacement = "below",
            className,
        },
        ref,
    ) {
        const [menuOpen, setMenuOpen] = useState(false);
        const wrapperRef = useRef<HTMLDivElement | null>(null);
        const triggerRef = useRef<HTMLButtonElement | null>(null);
        const menuRef = useRef<HTMLDivElement | null>(null);

        useImperativeHandle(ref, () => ({
            focusTrigger: () => triggerRef.current?.focus(),
        }));

        useEffect(() => {
            if (!menuOpen) return;
            const frame = requestAnimationFrame(() => {
                menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
            });
            return () => cancelAnimationFrame(frame);
        }, [menuOpen]);

        useEffect(() => {
            if (!menuOpen) return;
            const handlePointerDown = (event: PointerEvent) => {
                if (!wrapperRef.current?.contains(event.target as Node)) closeMenu();
            };
            document.addEventListener("pointerdown", handlePointerDown);
            return () => document.removeEventListener("pointerdown", handlePointerDown);
        }, [menuOpen]);

        const closeMenu = (restoreFocus = true) => {
            setMenuOpen(false);
            if (!restoreFocus) return;
            requestAnimationFrame(() => triggerRef.current?.focus());
        };

        const handleMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
            if (event.key === "Escape") {
                event.preventDefault();
                closeMenu();
                return;
            }
            if (event.key !== "Tab") return;

            const items = Array.from(
                menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [],
            );
            if (items.length === 0) return;
            const currentIndex = items.indexOf(document.activeElement as HTMLElement);
            const direction = event.shiftKey ? "backward" : "forward";
            const fallbackIndex = event.shiftKey ? items.length - 1 : 0;
            const nextIndex = nextFocusableIndex(
                currentIndex === -1 ? fallbackIndex : currentIndex,
                items.length,
                direction,
            );
            event.preventDefault();
            items[nextIndex]?.focus();
        };

        const handleManagement = () => {
            closeMenu(false);
            onOpenManagement();
        };

        const handleLogout = () => {
            closeMenu();
            onLogout();
        };

        const handleGovernance = () => {
            closeMenu(false);
            onOpenGovernance();
        };

        return (
            <div ref={wrapperRef} className={className ? `relative ${className}` : "relative"}>
                <button
                    ref={triggerRef}
                    type="button"
                    onClick={() => setMenuOpen((open) => !open)}
                    aria-label="用户菜单"
                    aria-haspopup="menu"
                    aria-expanded={menuOpen}
                    title="用户菜单"
                    className="grid h-11 w-11 place-items-center rounded-full bg-indigo/15 text-indigo transition hover:bg-indigo/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50"
                >
                    <UserRound className="h-4 w-4" aria-hidden="true" />
                    <span className="sr-only">{username.trim().slice(0, 1) || "用"}</span>
                </button>
                {menuOpen && (
                    <div
                        ref={menuRef}
                        role="menu"
                        aria-label="用户菜单"
                        onKeyDown={handleMenuKeyDown}
                        className={`absolute z-20 min-w-48 border border-ink/10 bg-white p-2 shadow-line ${
                            menuPlacement === "above"
                                ? "bottom-full left-0 mb-2"
                                : "right-0 top-full mt-2"
                        }`}
                    >
                        <div
                            role="group"
                            aria-label="当前用户"
                            className="px-3 py-2 text-sm text-ink/60"
                        >
                            {username}
                        </div>
                        {showManagement && (
                            <button
                                type="button"
                                role="menuitem"
                                tabIndex={0}
                                onClick={handleManagement}
                                className="flex min-h-10 w-full items-center px-3 text-left text-sm text-ink transition hover:bg-ink/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50"
                            >
                                用户管理
                            </button>
                        )}
                        {showGovernance && (
                            <button
                                type="button"
                                role="menuitem"
                                tabIndex={0}
                                onClick={handleGovernance}
                                className="flex min-h-10 w-full items-center gap-2 px-3 text-left text-sm text-ink transition hover:bg-ink/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50"
                            >
                                <Gauge className="h-4 w-4 text-indigo" aria-hidden="true" />
                                Agent 管理
                            </button>
                        )}
                        <button
                            type="button"
                            role="menuitem"
                            tabIndex={0}
                            onClick={handleLogout}
                            className="flex min-h-10 w-full items-center px-3 text-left text-sm text-ink transition hover:bg-ink/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50"
                        >
                            退出登录
                        </button>
                    </div>
                )}
            </div>
        );
    },
);

UserAvatarMenu.displayName = "UserAvatarMenu";
