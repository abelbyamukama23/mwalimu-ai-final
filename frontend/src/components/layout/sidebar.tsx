"use client";

import {
  Books,
  DotsThree,
  MagnifyingGlass,
  NotePencil,
  PlugsConnected,
} from "@phosphor-icons/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { AccountMenu } from "@/components/account/account-menu";
import { SearchChatsDialog } from "@/components/chat/search-chats-dialog";
import {
  ConfirmConversationDialog,
  RenameConversationDialog,
} from "@/components/chat/session-action-dialogs";
import { useAuthModal } from "@/components/auth/auth-modal";
import { useAuth } from "@/components/auth/auth-provider";
import {
  useArchiveSession,
  useDeleteSession,
  useRenameSession,
  useSessions,
} from "@/lib/chat/use-chat";
import { useToast } from "@/components/ui/toast";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { IconButton } from "@/components/ui/icon-button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

function NavItem({
  href,
  icon: Icon,
  label,
  active,
  trailing,
}: {
  href: string;
  icon: React.ComponentType<{ size?: number; weight?: "regular" | "bold" | "duotone" | "fill" | "light" | "thin"; className?: string; "aria-hidden"?: boolean }>;
  label: string;
  active?: boolean;
  trailing?: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "focus-ring flex items-center gap-2.5 rounded-sm px-3 py-2 text-14 transition-colors duration-150",
        active
          ? "bg-active font-medium text-accent"
          : "text-ink-secondary hover:bg-subtle hover:text-ink",
      )}
    >
      <Icon size={18} weight={active ? "duotone" : "regular"} aria-hidden className="shrink-0" />
      <span className="flex-1 truncate">{label}</span>
      {trailing}
    </Link>
  );
}


function SessionRow({ id, title, active }: { id: string; title: string; active?: boolean }) {
  const router = useRouter();
  const toast = useToast();
  const renameMutation = useRenameSession();
  const archiveMutation = useArchiveSession();
  const deleteMutation = useDeleteSession();
  const [dialog, setDialog] = useState<null | "rename" | "archive" | "delete">(null);
  const [renameValue, setRenameValue] = useState(title);

  const navigateAwayIfActive = () => {
    if (active) router.push("/chat/new");
  };

  const close = () => setDialog(null);

  return (
    <>
      <div
        className={cn(
          "group relative flex items-center rounded-sm transition-colors duration-150",
          active ? "bg-active" : "hover:bg-subtle",
        )}
      >
        <Link
          href={`/chat/${id}`}
          aria-current={active ? "page" : undefined}
          className={cn(
            "focus-ring min-w-0 flex-1 truncate rounded-sm px-3 py-2 text-14",
            active ? "font-medium text-accent" : "text-ink-secondary group-hover:text-ink",
          )}
        >
          {title}
        </Link>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <IconButton
              aria-label={`Actions for conversation "${title}"`}
              size="sm"
              className="mr-1 opacity-0 focus-visible:opacity-100 group-hover:opacity-100"
            >
              <DotsThree size={18} weight="bold" />

            </IconButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="right">
            <DropdownMenuLabel>
              Conversation actions
            </DropdownMenuLabel>
            <DropdownMenuItem
              onSelect={() => {
                setRenameValue(title);
                setDialog("rename");
              }}
            >
              Rename
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setDialog("archive")}>
              Archive
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setDialog("delete")}>
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <RenameConversationDialog
        open={dialog === "rename"}
        onOpenChange={(open) => {
          if (!open) close();
        }}
        value={renameValue}
        onChange={setRenameValue}
        pending={renameMutation.isPending}
        onSave={(newTitle) => {
          renameMutation.mutate(
            { sessionId: id, title: newTitle },
            {
              onSuccess: () => {
                toast("Conversation renamed");
                close();
              },
            },
          );
        }}
      />

      <ConfirmConversationDialog
        open={dialog === "archive"}
        onOpenChange={(open) => {
          if (!open) close();
        }}
        title="Archive this conversation?"
        description="It will be removed from your recent chats but not deleted. You can restore it again at any time."
        confirmLabel="Archive"
        pending={archiveMutation.isPending}
        onConfirm={() => {
          archiveMutation.mutate(id, {
            onSuccess: () => {
              toast("Conversation archived");
              close();
              navigateAwayIfActive();
            },
          });
        }}
      />

      <ConfirmConversationDialog
        open={dialog === "delete"}
        onOpenChange={(open) => {
          if (!open) close();
        }}
        title="Delete this conversation?"
        description="This permanently deletes the conversation and its messages. This can’t be undone."
        confirmLabel="Delete"
        destructive
        pending={deleteMutation.isPending}
        onConfirm={() => {
          deleteMutation.mutate(id, {
            onSuccess: () => {
              toast("Conversation deleted");
              close();
              navigateAwayIfActive();
            },
          });
        }}
      />
    </>
  );
}

export function SidebarContent() {
  const pathname = usePathname();
  const { user, status } = useAuth();
  const { openAuthModal } = useAuthModal();
  const [searchOpen, setSearchOpen] = useState(false);
  const { data: sessions } = useSessions();

  const recents = sessions ?? [];

  return (
    <div className="flex h-full flex-col gap-1 px-3 py-5">
      {/* New chat — understated primary action. */}
      <Link
        href="/chat/new"
        className="focus-ring mb-2 flex w-full items-center gap-2.5 rounded-sm border border-border bg-surface px-3 py-2 text-14 font-medium text-ink transition-colors duration-150 hover:border-border-strong hover:bg-subtle"
      >
        <NotePencil size={18} weight="duotone" aria-hidden className="shrink-0 text-accent" />
        New chat
      </Link>

      {/* Search chats — opens a centered modal. */}
      <button
        onClick={() => setSearchOpen(true)}
        className="focus-ring flex w-full items-center gap-2.5 rounded-sm px-3 py-2 text-14 text-ink-secondary transition-colors duration-150 hover:bg-subtle hover:text-ink"
      >
        <MagnifyingGlass size={18} aria-hidden className="shrink-0" />
        Search chats
      </button>

      <nav aria-label="Primary" className="space-y-0.5">
        <NavItem
          href="/libraries"
          icon={Books}
          label="Libraries"
          active={pathname.startsWith("/libraries")}
        />
        <NavItem
          href="/connections"
          icon={PlugsConnected}
          label="Connections"
          active={pathname.startsWith("/connections") || pathname.startsWith("/connectors")}
        />
      </nav>



      <p className="mb-1 mt-5 px-3 text-11 font-medium tracking-wide text-ink-tertiary">
        RECENT
      </p>
      <div className="flex-1 space-y-0.5 overflow-y-auto">
        {recents.map((s) => (
          <SessionRow
            key={s.id}
            id={s.id}
            title={s.title}
            active={pathname === `/chat/${s.id}`}
          />
        ))}
        {recents.length === 0 && (
          <p className="px-3 py-2 text-13 text-ink-tertiary">No chats yet.</p>
        )}
      </div>

      <Separator className="my-2" />

      {status === "authenticated" ? (
        <AccountMenu
          trigger={
            <button className="focus-ring flex items-center gap-2.5 rounded-sm px-2 py-2 text-left transition-colors duration-150 hover:bg-subtle">
              <Avatar initials={user?.email?.slice(0, 2).toUpperCase() ?? "MW"} size={34} />
              <span className="min-w-0">
                <span className="block truncate text-13 font-medium text-ink">
                  {user ? user.email : "Signed in"}
                </span>
              </span>
            </button>
          }
        />
      ) : (
        <button
          onClick={() => openAuthModal()}
          className="focus-ring flex w-full items-center gap-2.5 rounded-sm px-2 py-2 text-left text-13 font-medium text-ink transition-colors duration-150 hover:bg-subtle"
        >
          <Avatar initials="MW" size={34} />
          <span className="block truncate">Log in or sign up</span>
        </button>
      )}

      <SearchChatsDialog
        open={searchOpen}
        onOpenChange={setSearchOpen}
        sessions={recents}
      />
    </div>
  );
}
