import {
  Body,
  Container,
  Head,
  Heading,
  Html,
  Preview,
  Section,
  Text,
} from "@react-email/components";
import * as React from "react";

interface VerificationOtpEmailProps {
  otp?: string;
}

export function VerificationOtpEmail({ otp = "482913" }: VerificationOtpEmailProps) {
  return (
    <Html>
      <Head />
      <Preview>Your Mwalimu verification code is {otp}</Preview>
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
            <Heading style={heading}>Verify your email address</Heading>
            <Text style={paragraph}>
              Welcome to Mwalimu. To complete your account registration and access your personalized academic workspace, enter the verification code below:
            </Text>

            <Section style={codeContainer}>
              <Text style={codeText}>{otp}</Text>
            </Section>

            <Text style={note}>
              <strong>Note:</strong> This verification code expires in <strong>10 minutes</strong> and can only be used once.
            </Text>

            <Text style={subnote}>
              If you did not request this account, you can safely disregard this email.
            </Text>
          </Section>

          {/* Footer */}
          <Section style={footer}>
            <Text style={footerText}>
              Mwalimu &middot; Contextual AI Teaching &amp; Study Platform
            </Text>
          </Section>
        </Container>
      </Body>
    </Html>
  );
}

export default VerificationOtpEmail;

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
  margin: "0 0 24px 0",
  fontSize: "14px",
  lineHeight: "22px",
  color: "#71717A",
};

const codeContainer: React.CSSProperties = {
  backgroundColor: "#F4F4F5",
  border: "1px solid #E4E4E7",
  borderRadius: "8px",
  padding: "16px 24px",
  textAlign: "center",
  margin: "0 0 24px 0",
};

const codeText: React.CSSProperties = {
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
  fontSize: "32px",
  fontWeight: "700",
  letterSpacing: "6px",
  color: "#18181B",
  margin: 0,
};

const note: React.CSSProperties = {
  margin: "0 0 8px 0",
  fontSize: "13px",
  lineHeight: "20px",
  color: "#71717A",
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
