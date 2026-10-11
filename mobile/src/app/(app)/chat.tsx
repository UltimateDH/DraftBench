import { useRef, useState } from 'react';
import {
  ActivityIndicator, FlatList, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View,
} from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '@/context/AuthContext';
import { askChat, ChatTurn } from '@/lib/api';
import { colors } from '@/lib/theme';

type Msg = { id: string; role: 'user' | 'assistant'; content: string; error?: boolean };

const SUGGESTIONS = [
  'Summarize this in 5 key points',
  'List the important terms and definitions',
  'Suggest 5 quiz questions with answers',
];

export default function Chat() {
  const { token } = useAuth();
  const { ids, names } = useLocalSearchParams<{ ids: string; names: string }>();
  const materialIds = (ids ?? '').split(',').map(Number).filter(Boolean);
  const fileNames = (names ?? '').split('|').filter(Boolean);

  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const listRef = useRef<FlatList<Msg>>(null);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || sending || !token) return;
    const history: ChatTurn[] = messages.filter((m) => !m.error).map((m) => ({ role: m.role, content: m.content }));
    setMessages((p) => [...p, { id: `u${Date.now()}`, role: 'user', content: q }]);
    setInput('');
    setSending(true);
    try {
      const reply = await askChat(token, materialIds, q, history);
      setMessages((p) => [...p, { id: `a${Date.now()}`, role: 'assistant', content: reply }]);
    } catch (e: any) {
      setMessages((p) => [...p, { id: `e${Date.now()}`, role: 'assistant', content: e.message, error: true }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <View style={s.screen}>
      <StatusBar style="light" />
      <SafeAreaView edges={['top']} style={s.header}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Text style={s.back}>‹ Back</Text></Pressable>
        <Text style={s.title}>Ask your materials</Text>
        <Text style={s.files} numberOfLines={1}>{fileNames.join(', ')}</Text>
      </SafeAreaView>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={s.body}>
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(m) => m.id}
          contentContainerStyle={s.list}
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
          keyboardShouldPersistTaps="handled"
          ListHeaderComponent={
            messages.length === 0 ? (
              <View style={s.intro}>
                <Text style={s.introTitle}>What would you like to know?</Text>
                <Text style={s.introSub}>Ask anything about the selected files. Answers come only from your material.</Text>
                {SUGGESTIONS.map((q) => (
                  <Pressable key={q} onPress={() => send(q)} style={s.chip}><Text style={s.chipText}>{q}</Text></Pressable>
                ))}
              </View>
            ) : null
          }
          renderItem={({ item }) => (
            <View style={[s.bubble, item.role === 'user' ? s.user : s.bot, item.error && s.errBubble]}>
              <Text style={[s.msg, item.role === 'user' && { color: '#fff' }, item.error && { color: colors.danger }]} selectable>
                {item.content}
              </Text>
            </View>
          )}
          ListFooterComponent={
            sending ? (
              <View style={[s.bubble, s.bot, { flexDirection: 'row', gap: 8, alignItems: 'center' }]}>
                <ActivityIndicator size="small" color={colors.primary} />
                <Text style={s.msg}>Reading your material…</Text>
              </View>
            ) : null
          }
        />

        <SafeAreaView edges={['bottom']} style={s.inputBar}>
          <View style={s.inputRow}>
            <TextInput
              value={input}
              onChangeText={setInput}
              placeholder="Ask a question…"
              placeholderTextColor="#A99FC0"
              multiline
              style={s.input}
              onSubmitEditing={() => send(input)}
            />
            <Pressable onPress={() => send(input)} disabled={sending || !input.trim()} style={[s.send, (sending || !input.trim()) && { opacity: 0.4 }]}>
              <Text style={s.sendText}>Send</Text>
            </Pressable>
          </View>
        </SafeAreaView>
      </KeyboardAvoidingView>
    </View>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.primary },
  header: { paddingHorizontal: 20, paddingBottom: 36 },
  back: { color: '#DDD0FA', fontWeight: '700', fontSize: 15, marginTop: 8 },
  title: { color: '#fff', fontSize: 24, fontWeight: '800', marginTop: 10 },
  files: { color: '#DDD0FA', fontSize: 13, marginTop: 4 },

  body: { flex: 1, backgroundColor: colors.paper, borderTopLeftRadius: 32, borderTopRightRadius: 32, marginTop: -24, overflow: 'hidden' },
  list: { padding: 20, gap: 10, width: '100%', maxWidth: 720, alignSelf: 'center', flexGrow: 1 },

  intro: { marginBottom: 8 },
  introTitle: { fontSize: 20, fontWeight: '800', color: colors.text },
  introSub: { color: colors.muted, marginTop: 4, marginBottom: 16, lineHeight: 21 },
  chip: { backgroundColor: colors.soft, borderRadius: 14, paddingVertical: 12, paddingHorizontal: 16, marginBottom: 8 },
  chipText: { color: colors.primary, fontWeight: '600', fontSize: 15 },

  bubble: { maxWidth: '88%', borderRadius: 18, paddingVertical: 10, paddingHorizontal: 14 },
  user: { alignSelf: 'flex-end', backgroundColor: colors.primary, borderBottomRightRadius: 6 },
  bot: { alignSelf: 'flex-start', backgroundColor: colors.soft, borderBottomLeftRadius: 6 },
  errBubble: { backgroundColor: '#FDECEC' },
  msg: { fontSize: 16, lineHeight: 23, color: colors.text },

  inputBar: { borderTopWidth: 1, borderTopColor: colors.soft, backgroundColor: colors.paper, paddingHorizontal: 14, paddingTop: 10 },
  inputRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 10, width: '100%', maxWidth: 720, alignSelf: 'center', paddingBottom: 8 },
  input: {
    flex: 1, maxHeight: 120, backgroundColor: colors.soft, borderRadius: 16, paddingHorizontal: 16, paddingVertical: 12,
    fontSize: 16, color: colors.text,
    ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : {}),
  },
  send: { backgroundColor: colors.primary, borderRadius: 14, paddingHorizontal: 18, paddingVertical: 13 },
  sendText: { color: '#fff', fontWeight: '700', fontSize: 15 },
});
