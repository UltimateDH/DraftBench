import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, ScrollView, StyleSheet, Text, TextInput, View, Platform } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '@/context/AuthContext';
import { ErrorText, PrimaryButton } from '@/components/AuthUI';
import { getDownloadUrl, getJob, OutputKind, startGeneration } from '@/lib/api';
import { colors } from '@/lib/theme';

// Keep these in sync with the subject names in your curriculum JSON (the RAG filters on them).
const SUBJECTS = [
  'Mathematics', 'Science', 'Physics', 'Chemistry', 'Biology', 'English', 'Nepali',
  'Social Studies', 'Health', 'Computer Science', 'Economics', 'Accountancy',
];
const GRADES = Array.from({ length: 12 }, (_, i) => i + 1);
const QUESTION_COUNTS = [5, 8, 10, 15];

const TITLES: Record<OutputKind, string> = {
  presentation: 'Create slides',
  document: 'Create lesson plan & IEP',
  quiz: 'Create a quiz',
  braille: 'Create braille cards',
  nsl: 'Create sign language cards',
};
const PROMPTS: Record<OutputKind, string> = {
  presentation: 'Create a short lesson presentation about ',
  document: 'Create a lesson plan with an IEP goal about ',
  quiz: 'Create a quiz about ',
  braille: 'Create braille cards for a lesson about ',
  nsl: 'Create sign language cards for a lesson about ',
};
const NOTES: Partial<Record<OutputKind, string>> = {
  quiz: 'The quiz sheet comes with an answer key on the last page for the teacher.',
  braille: 'Dot patterns are drawn on the page. Please have a braille reader check them before classroom use.',
  nsl: 'Gestures are suggestions unless they come from your NSL glossary. A signer should check them.',
};

type Phase = 'form' | 'working' | 'done' | 'failed';

export default function Generate() {
  const { token } = useAuth();
  const { output, ids, names } = useLocalSearchParams<{ output: OutputKind; ids?: string; names?: string }>();
  const materialIds = (ids ?? '').split(',').map(Number).filter(Boolean);
  const fileNames = (names ?? '').split('|').filter(Boolean);

  const [prompt, setPrompt] = useState(PROMPTS[output] ?? PROMPTS.presentation);
  const [grade, setGrade] = useState(1);
  const [subject, setSubject] = useState('Mathematics');
  const [language, setLanguage] = useState<'nepali' | 'english'>('nepali');
  const [numQuestions, setNumQuestions] = useState(8);
  const [phase, setPhase] = useState<Phase>('form');
  const [step, setStep] = useState('');
  const [error, setError] = useState('');
  const [jobId, setJobId] = useState('');
  const [filename, setFilename] = useState('');
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const busy = useRef(false);

  const stopPolling = () => { if (timer.current) clearInterval(timer.current); timer.current = null; };
  useEffect(() => stopPolling, []);

  const start = async () => {
    if (!token || busy.current) return; // ignore double taps
    if (prompt.trim().length < 10) return setError('Describe what you want in a few more words.');
    busy.current = true;
    setError('');
    stopPolling();
    setPhase('working'); // show progress right away instead of waiting for the server
    setStep('Starting...');
    try {
      const id = await startGeneration(token, { prompt: prompt.trim(), output, grade, subject, language, material_ids: materialIds, num_questions: output === 'quiz' ? numQuestions : undefined });
      setStep('Waiting to start...');
      timer.current = setInterval(async () => {
        try {
          const j = await getJob(token, id);
          setStep(j.step);
          if (j.status === 'done') {
            stopPolling(); busy.current = false;
            setJobId(id); // only now, so "Open file" always uses the job that actually finished
            setFilename(j.filename ?? '');
            setPhase('done');
          }
          if (j.status === 'failed') { stopPolling(); busy.current = false; setError(j.error ?? 'Generation failed.'); setPhase('failed'); }
        } catch (e: any) { stopPolling(); busy.current = false; setError(e.message); setPhase('failed'); }
      }, 2500);
    } catch (e: any) {
      busy.current = false;
      setPhase('form');
      setError(e.message);
    }
  };

  const openFile = async () => {
    if (!token) return;
    try {
      const url = await getDownloadUrl(token, jobId);
      await Linking.openURL(url);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const reset = () => { stopPolling(); busy.current = false; setPhase('form'); setError(''); };

  return (
    <View style={s.screen}>
      <StatusBar style="light" />
      <SafeAreaView edges={['top']} style={s.header}>
        <Pressable onPress={() => router.back()} hitSlop={10}><Text style={s.back}>‹ Back</Text></Pressable>
        <Text style={s.title}>{TITLES[output] ?? 'Create'}</Text>
        <Text style={s.files} numberOfLines={1}>
          {fileNames.length ? `From: ${fileNames.join(', ')}` : 'No files selected: using your description and the curriculum'}
        </Text>
      </SafeAreaView>

      <ScrollView style={s.body} contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
        {phase === 'form' && (
          <>
            <Text style={s.label}>What should it cover?</Text>
            <TextInput value={prompt} onChangeText={setPrompt} multiline style={s.textarea} placeholderTextColor="#A99FC0" />

            <Text style={s.label}>Grade</Text>
            <View style={s.chips}>
              {GRADES.map((g) => <Chip key={g} label={String(g)} on={grade === g} onPress={() => setGrade(g)} />)}
            </View>

            <Text style={s.label}>Subject</Text>
            <View style={s.chips}>
              {SUBJECTS.map((x) => <Chip key={x} label={x} on={subject === x} onPress={() => setSubject(x)} />)}
            </View>

            {output === 'quiz' && (
              <>
                <Text style={s.label}>Number of questions</Text>
                <View style={s.chips}>
                  {QUESTION_COUNTS.map((n) => <Chip key={n} label={String(n)} on={numQuestions === n} onPress={() => setNumQuestions(n)} />)}
                </View>
              </>
            )}

            <Text style={s.label}>Language</Text>
            <View style={s.chips}>
              <Chip label="नेपाली" on={language === 'nepali'} onPress={() => setLanguage('nepali')} />
              <Chip label="English" on={language === 'english'} onPress={() => setLanguage('english')} />
            </View>

            <View style={{ height: 8 }} />
            <ErrorText message={error} />
            <PrimaryButton title="Generate" onPress={start} />
            <Text style={s.note}>This runs on your own server and can take a few minutes.</Text>
            {NOTES[output] ? <Text style={s.note}>{NOTES[output]}</Text> : null}
          </>
        )}

        {phase === 'working' && (
          <View style={s.center}>
            <ActivityIndicator size="large" color={colors.primary} />
            <Text style={s.stepText}>{step}</Text>
            <Text style={s.note}>Keep this screen open. Slow models can take several minutes.</Text>
          </View>
        )}

        {phase === 'done' && (
          <View style={s.center}>
            <Text style={s.doneTitle}>Your file is ready</Text>
            <Text style={s.note}>{filename}</Text>
            <View style={{ height: 16, width: '100%' }} />
            <ErrorText message={error} />
            <PrimaryButton title="Open file" onPress={openFile} />
            <Pressable onPress={reset} style={{ marginTop: 18 }}><Text style={s.link}>Create another</Text></Pressable>
          </View>
        )}

        {phase === 'failed' && (
          <View style={s.center}>
            <Text style={s.doneTitle}>That didn't work</Text>
            <ErrorText message={error} />
            <PrimaryButton title="Try again" onPress={reset} />
          </View>
        )}
      </ScrollView>
    </View>
  );
}

function Chip({ label, on, onPress }: { label: string; on: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[s.chip, on && s.chipOn]}>
      <Text style={[s.chipText, on && { color: '#fff' }]}>{label}</Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.primary },
  header: { paddingHorizontal: 20, paddingBottom: 36 },
  back: { color: '#DDD0FA', fontWeight: '700', fontSize: 15, marginTop: 8 },
  title: { color: '#fff', fontSize: 24, fontWeight: '800', marginTop: 10 },
  files: { color: '#DDD0FA', fontSize: 13, marginTop: 4 },

  body: { flex: 1, backgroundColor: colors.paper, borderTopLeftRadius: 32, borderTopRightRadius: 32, marginTop: -24 },
  content: { padding: 22, paddingBottom: 60, width: '100%', maxWidth: 720, alignSelf: 'center' },

  label: { fontSize: 14, fontWeight: '700', color: colors.text, marginTop: 18, marginBottom: 8 },
  textarea: {
    backgroundColor: colors.soft, borderRadius: 14, padding: 14, minHeight: 96, fontSize: 16, color: colors.text, textAlignVertical: 'top',
    ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : {}),
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { backgroundColor: colors.soft, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 999 },
  chipOn: { backgroundColor: colors.primary },
  chipText: { color: colors.primary, fontWeight: '700', fontSize: 14 },

  center: { alignItems: 'center', paddingTop: 40 },
  stepText: { marginTop: 18, fontSize: 17, fontWeight: '700', color: colors.text, textAlign: 'center' },
  doneTitle: { fontSize: 22, fontWeight: '800', color: colors.text, marginBottom: 6 },
  note: { color: colors.muted, fontSize: 13, marginTop: 12, textAlign: 'center' },
  link: { color: colors.primary, fontWeight: '700', fontSize: 15 },
});
