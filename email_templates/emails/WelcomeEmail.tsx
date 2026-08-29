import {
  Body,
  Button,
  Container,
  Head,
  Heading,
  Html,
  Preview,
  Section,
  Text,
} from "@react-email/components";
import * as React from "react";

interface WelcomeEmailProps {
  displayName?: string;
  workspaceUrl?: string;
}

export function WelcomeEmail({
  displayName = "",
  workspaceUrl = "https://mwalimu.ai/chat/new",
}: WelcomeEmailProps) {
  const greeting = displayName ? `, ${displayName}` : "";

  return (
    <Html>
      <Head />
      <Preview>Welcome to Mwalimu — your contextual AI learning workspace</Preview>
      <Body style={main}>
        <Container style={container}>
          {/* Header */}
          <Section style={header}>
            <table cellPadding="0" cellSpacing="0" style={{ borderCollapse: "collapse" }}>
              <tbody>
                <tr>
                  <td style={logoBox}>M</td>
                  <td style={logoText}>Mwalimu</td>
                </tr>
              </tbody>
            </table>
          </Section>

          {/* Content */}
          <Section style={content}>
            <Heading style={heading}>Welcome to Mwalimu{greeting}!</Heading>
            <Text style={paragraph}>
              Your account is ready. Mwalimu provides personalized AI tutors grounded in your curriculum, course documents, and local East African context.
            </Text>
            <Text style={paragraph}>
              You can upload lecture notes, link study drives, and engage in interactive, step-by-step Socratic learning.
            </Text>

            <Section style={buttonContainer}>
              <Button style={button} href={workspaceUrl}>
                Open Learning Workspace
              </Button>
            </Section>

            <Text style={subnote}>
              If you have any questions or feedback, simply reply to this email. We are here to support your learning journey.
            </Text>
          </Section>

          {/* Footer */}
          <Section style={footer}>
            <Text style={footerText}>
              Mwalimu &middot; Learn with deep contextual understanding
            </Text>
          </Section>
        </Container>
      </Body>
    </Html>
  );
}

export default WelcomeEmail;

const main: React.CSSProperties = {
  backgroundColor: "#FBFBFB",
  fontFamily:
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
  margin: 0,
  padding: "40px 16px",
};

const container: React.CSSProperties = {
  maxWidth: "480px",
  backgroundColor: "#FFFFFF",
  border: "1px solid #E4E4E7",
  borderRadius: "12px",
  overflow: "hidden",
  margin: "0 auto",
  boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
};

const header: React.CSSProperties = {
  padding: "24px 32px",
  borderBottom: "1px solid #F4F4F5",
};

const logoBox: React.CSSProperties = {
  width: "28px",
  height: "28px",
  backgroundColor: "#18181B",
  borderRadius: "6px",
  textAlign: "center",
  color: "#FFFFFF",
  fontWeight: "bold",
  fontSize: "16px",
  lineHeight: "28px",
};

const logoText: React.CSSProperties = {
  paddingLeft: "12px",
  fontSize: "17px",
  fontWeight: "600",
  color: "#18181B",
  letterSpacing: "-0.01em",
};

const content: React.CSSProperties = {
  padding: "32px",
};

const heading: React.CSSProperties = {
  margin: "0 0 12px 0",
  fontSize: "20px",
  fontWeight: "600",
  color: "#18181B",
  letterSpacing: "-0.02em",
};

const paragraph: React.CSSProperties = {
  margin: "0 0 16px 0",
  fontSize: "14px",
  lineHeight: "22px",
  color: "#71717A",
};

const buttonContainer: React.CSSProperties = {
  margin: "24px 0 28px 0",
};

const button: React.CSSProperties = {
  backgroundColor: "#18181B",
  color: "#FFFFFF",
  padding: "12px 24px",
  borderRadius: "8px",
  fontWeight: "600",
  fontSize: "14px",
  textDecoration: "none",
  textAlign: "center",
  display: "inline-block",
  boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
};

const subnote: React.CSSProperties = {
  margin: 0,
  fontSize: "13px",
  lineHeight: "20px",
  color: "#A1A1AA",
};

const footer: React.CSSProperties = {
  padding: "20px 32px",
  backgroundColor: "#FAFAFA",
  borderTop: "1px solid #F4F4F5",
  textAlign: "center",
};

const footerText: React.CSSProperties = {
  margin: 0,
  fontSize: "12px",
  color: "#A1A1AA",
};
