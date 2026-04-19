// Global state for the selected topic filter
let selectedTopicId = null;

export function getSelectedTopicId() { return selectedTopicId; }
export function setSelectedTopicId(id) { selectedTopicId = id; }
