"use client";

import { useParams } from "next/navigation";
import { ChatView } from "@/components/chat/chat-view";

/**
 * Conversation route. Renders the shared ChatView which loads a session from
 * the mock chat layer (frontend-first until the sessions API is connected).
 */
export default function ConversationPage() {
  const { sessionId } = useParams();
  return <ChatView sessionId={typeof sessionId === "string" ? sessionId : ""} />;
}
