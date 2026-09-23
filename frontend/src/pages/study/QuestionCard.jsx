import { ArrowRight, CheckCircle, X, Loader2, Eye, EyeOff, AlertCircle } from 'lucide-react'
import Ruby from '../../components/Ruby'
import SpeakButton from '../../components/SpeakButton'
import { Skeleton, SkeletonLine } from '../../components/Skeleton'
import { CLOZE_BLANK, RATING_COLOR, RATING_LABEL, isAnswerAccepted } from './studyLogic'

const MODE_HEADING = {
  sentence_build: 'Translate to Japanese',
  grammar_drill: 'Choose the correct usage',
  cloze: 'Recall the missing word',
  fill_blank: 'Fill in the blank',
}

const VERDICT_STYLE = {
  correct: { border: 'border-green-500/30', text: 'text-green-400', Icon: CheckCircle, label: 'Correct!' },
  partial: { border: 'border-yellow-500/30', text: 'text-yellow-400', Icon: AlertCircle, label: 'Almost there' },
  incorrect: { border: 'border-red-500/30', text: 'text-red-400', Icon: X, label: 'Incorrect' },
}

/** The AI's verdict on a sentence_build answer, or its loading/error state. */
function SentenceBuildResult({ evaluating, evaluation, error, retry, userAnswer, question }) {
  if (evaluating) {
    return (
      <div className="border-t border-gray-700 pt-4 flex items-center gap-2 text-gray-500 text-sm">
        <Loader2 size={15} className="animate-spin" /> Evaluating your answer…
      </div>
    )
  }
  if (!evaluation) {
    return error ? (
      <div className="border-t border-gray-700 pt-4 space-y-3">
        <div className="flex items-center gap-2 text-sm text-red-300">
          <AlertCircle size={15} /> {error}
        </div>
        <button onClick={retry}
          className="bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-500 text-sm">
          Try again
        </button>
      </div>
    ) : null
  }
  const { verdict, feedback, corrected } = evaluation
  const style = VERDICT_STYLE[verdict] || VERDICT_STYLE.incorrect
  return (
    <div className={`border-t pt-4 space-y-2 ${style.border}`}>
      <div className={`flex items-center gap-2 font-medium ${style.text}`}>
        <style.Icon size={18} /> {style.label}
      </div>
      <div className="text-sm">
        <span className="text-gray-500">Your answer: </span>
        <Ruby text={userAnswer} className="text-gray-200" />
      </div>
      {feedback && <div className="text-sm text-gray-400">{feedback}</div>}
      {corrected && (
        <div className="text-sm">
          <span className="text-gray-500">Corrected: </span>
          <Ruby text={corrected} className="text-gray-200" />
        </div>
      )}
      <div className="text-sm text-gray-500">Reference answer:</div>
      <Ruby text={question.answer} className="text-lg font-medium text-gray-100" />
    </div>
  )
}

/** Right/wrong result for the exact-match modes (cloze, fill_blank, grammar_drill). */
function AnswerResult({ mode, question, userAnswer }) {
  const isCorrect = isAnswerAccepted(userAnswer, question)
  const style = VERDICT_STYLE[isCorrect ? 'correct' : 'incorrect']
  // For cloze the sentence with the blank filled back in is the thing worth
  // reading aloud, not the bare word.
  const spoken = mode === 'cloze'
    ? question.prompt.replace(CLOZE_BLANK, question.answer)
    : question.answer
  return (
    <div className={`border-t pt-4 space-y-2 ${style.border}`}>
      <div className={`flex items-center gap-2 font-medium ${style.text}`}>
        <style.Icon size={18} /> {style.label}
      </div>
      {!isCorrect && userAnswer && (
        <div className="text-sm text-red-300/70">
          Your answer: <Ruby text={userAnswer} />
        </div>
      )}
      <div className="text-sm text-gray-500">Correct answer:</div>
      <div className="flex items-center gap-1">
        <Ruby text={question.answer} className="text-lg font-medium text-gray-100" />
        <SpeakButton text={spoken} label="Read the sentence aloud" />
      </div>
      {mode === 'cloze' && question.translation && (
        <div className="text-sm text-gray-500">{question.translation}</div>
      )}
    </div>
  )
}

export default function QuestionCard({
  mode, question, userAnswer, setUserAnswer, answerChecked, checkAnswer,
  evaluating, evaluation, hintsRevealed, setHintsRevealed,
  translationRevealed, setTranslationRevealed, error, retry,
  exitStudy, submitting, onRate, practice, progress,
}) {
  // AI-question modes (fill_blank, grammar_drill, sentence_build) have an
  // objectively correct answer, so the SRS rating is derived from correctness
  // instead of asking the learner to self-grade.
  const derivedRating = mode === 'sentence_build'
    ? (evaluation?.verdict === 'correct' ? 'good' : evaluation?.verdict === 'partial' ? 'hard' : 'again')
    : (question && isAnswerAccepted(userAnswer, question) ? 'good' : 'again')

  const continueControl = (
    <div className="space-y-2">
      {error && (
        <div className="flex items-center gap-2 text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
          <AlertCircle size={15} /> {error}
        </div>
      )}
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs text-gray-500">
          {practice ? 'Rated' : 'Scheduled as'}{' '}
          <span className={RATING_COLOR[derivedRating]}>{RATING_LABEL[derivedRating]}</span>
        </span>
        <button
          onClick={() => onRate(derivedRating)}
          disabled={submitting}
          className="bg-indigo-600 text-white px-6 py-2.5 rounded-xl font-medium hover:bg-indigo-500 disabled:opacity-50 flex items-center gap-1.5"
        >
          Next <ArrowRight size={16} />
        </button>
      </div>
    </div>
  )

  return (
    <div className="max-w-lg mx-auto space-y-4">
      <div className="flex justify-between items-center text-sm text-gray-500">
        <span>{progress}</span>
        <button onClick={exitStudy} className="text-gray-500 hover:text-gray-300">Exit</button>
      </div>

      {question ? (
        <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6 space-y-4">
          <div className="text-sm text-gray-500 uppercase font-medium">
            {MODE_HEADING[mode]}
          </div>

          {mode === 'sentence_build' ? (
            <>
              <div className="text-xl font-medium text-gray-100 leading-relaxed">
                {question.prompt}
              </div>
              {(question.vocabulary?.length > 0 || question.context) && (
                <div className="text-sm">
                  <button
                    onClick={() => setHintsRevealed(v => !v)}
                    className="flex items-center gap-1.5 text-gray-600 hover:text-gray-400 transition-colors"
                  >
                    {hintsRevealed ? <EyeOff size={13} /> : <Eye size={13} />}
                    {hintsRevealed ? 'Hide' : 'Show'} hints
                  </button>
                  {hintsRevealed && (
                    <div className="mt-2 space-y-2">
                      {question.vocabulary?.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          {question.vocabulary.map((v, i) => (
                            <span
                              key={i}
                              className="inline-flex items-baseline gap-1.5 bg-gray-800 border border-gray-700 rounded-lg px-2.5 py-1 text-sm"
                            >
                              <Ruby text={v.japanese} className="text-gray-100" />
                              {v.meaning && <span className="text-gray-500 text-xs">{v.meaning}</span>}
                            </span>
                          ))}
                        </div>
                      )}
                      {question.context && <div className="text-gray-500">{question.context}</div>}
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <>
              <Ruby text={question.prompt} className="text-xl" />
              {question.context && <div className="text-sm text-gray-500">{question.context}</div>}
              {mode === 'cloze' && (
                <div className="text-xs text-gray-600">Kanji or kana both count.</div>
              )}
            </>
          )}

          {question.translation && mode !== 'sentence_build' && (
            <div className="text-sm">
              <button
                onClick={() => setTranslationRevealed(v => !v)}
                className="flex items-center gap-1.5 text-gray-600 hover:text-gray-400 transition-colors"
              >
                {translationRevealed ? <EyeOff size={13} /> : <Eye size={13} />}
                {translationRevealed ? 'Hide' : 'Show'} translation
              </button>
              {translationRevealed && (
                <div className="mt-1.5 text-gray-500">{question.translation}</div>
              )}
            </div>
          )}

          {question.options.length > 0 && !answerChecked && (
            <div className="grid grid-cols-2 gap-2">
              {question.options.map((opt, i) => (
                <button key={i} onClick={() => { setUserAnswer(opt); checkAnswer() }}
                  className="border border-gray-700 rounded-lg px-3 py-2 text-left hover:border-indigo-500/50 hover:bg-indigo-500/10 transition-colors">
                  <Ruby text={opt} />
                </button>
              ))}
            </div>
          )}

          {question.options.length === 0 && !answerChecked && (
            <div>
              <input
                value={userAnswer}
                onChange={e => setUserAnswer(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && userAnswer && checkAnswer()}
                className="w-full bg-gray-800 border border-gray-700 text-gray-100 rounded-lg px-3 py-2 jp-text focus:ring-2 focus:ring-indigo-500 outline-none"
                placeholder="Type your answer..."
                autoFocus
              />
              <button onClick={checkAnswer} disabled={!userAnswer}
                className="mt-2 w-full bg-indigo-600 text-white py-2 rounded-lg font-medium hover:bg-indigo-500 disabled:opacity-50">
                Check
              </button>
            </div>
          )}

          {answerChecked && (mode === 'sentence_build'
            ? (
              <SentenceBuildResult
                evaluating={evaluating} evaluation={evaluation} error={error} retry={retry}
                userAnswer={userAnswer} question={question}
              />
            )
            : <AnswerResult mode={mode} question={question} userAnswer={userAnswer} />
          )}
        </div>
      ) : error ? (
        <div className="bg-gray-900 rounded-2xl border border-red-500/30 p-6 space-y-3 text-center">
          <X className="mx-auto text-red-400" size={28} />
          <div className="text-sm text-red-300/90">{error}</div>
          <div className="flex gap-2 justify-center pt-1">
            <button onClick={retry}
              className="bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-500 text-sm">
              Try again
            </button>
            <button onClick={exitStudy}
              className="border border-gray-700 text-gray-300 px-4 py-2 rounded-lg hover:bg-gray-800 text-sm">
              Exit
            </button>
          </div>
        </div>
      ) : (
        <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6 space-y-4">
          <SkeletonLine width="40%" className="h-3" />
          <SkeletonLine width="85%" className="h-5" />
          <div className="grid grid-cols-2 gap-2 pt-2">
            <Skeleton className="h-10 rounded-lg" />
            <Skeleton className="h-10 rounded-lg" />
            <Skeleton className="h-10 rounded-lg" />
            <Skeleton className="h-10 rounded-lg" />
          </div>
        </div>
      )}

      {answerChecked && (mode !== 'sentence_build' || evaluation) && continueControl}
    </div>
  )
}
