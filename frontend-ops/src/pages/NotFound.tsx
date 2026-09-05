import { Center, Stack, Text, Title } from "@mantine/core";

export default function NotFound() {
  return (
    <Center mih="60vh">
      <Stack align="center" gap="xs">
        <Title order={1} fz={64} c="dimmed">
          404
        </Title>
        <Text c="dimmed">Page not found.</Text>
      </Stack>
    </Center>
  );
}
