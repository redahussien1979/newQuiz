"""Template registry. To add a template: create a module with NAME, EXAMPLE and a class
that has .base_duration, .dur, .fps, .silences, .render(t) -> PIL RGB image and .sound(mixer),
then register it below."""
from . import idiom_cards, mcq, news, quiz, text, timeline, torn_pad, vocab, words_video

TEMPLATES = {
    "timeline": (timeline.NAME, timeline.TimelineVideo, timeline.EXAMPLE),
    "quiz": (quiz.NAME, quiz.QuizVideo, quiz.EXAMPLE),
    "mcq": (mcq.NAME, mcq.MCQVideo, mcq.EXAMPLE),
    "vocab": (vocab.NAME, vocab.VocabVideo, vocab.EXAMPLE),
    "text": (text.NAME, text.make_video, text.EXAMPLE),
    "news": (news.NAME, news.NewsVideo, news.EXAMPLE),
    "wordsvideo": (words_video.NAME, words_video.WordsVideo, words_video.EXAMPLE),
    "idiomcards": (idiom_cards.NAME, idiom_cards.IdiomCards, idiom_cards.EXAMPLE),
    "tornpad": (torn_pad.NAME, torn_pad.TornPad, torn_pad.EXAMPLE),
}
