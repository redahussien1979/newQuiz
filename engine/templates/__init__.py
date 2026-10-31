"""Template registry. To add a template: create a module with NAME, EXAMPLE and a class
that has .base_duration, .dur, .fps, .silences, .render(t) -> PIL RGB image and .sound(mixer),
then register it below."""
from . import mcq, quiz, timeline

TEMPLATES = {
    "timeline": (timeline.NAME, timeline.TimelineVideo, timeline.EXAMPLE),
    "quiz": (quiz.NAME, quiz.QuizVideo, quiz.EXAMPLE),
    "mcq": (mcq.NAME, mcq.MCQVideo, mcq.EXAMPLE),
}
