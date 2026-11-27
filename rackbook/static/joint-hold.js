/* Joint hold notes for the logger (#154). Reads host monitoring state only; it never changes planned
   weights, training maxes, top sets or the workout. A held lift shows a note until the athlete records
   a decision in the joint coaching call. */
const JointHold = (() => {
  let held = new Map();
  async function load() {
    try {
      const response = await fetch('/api/joint/status');
      if (!response.ok) return;
      const status = await response.json();
      const regions = (status.call && status.call.regions) || [];
      const name = regions.length === 2 ? 'joint' : regions[0] + '-joint';
      held = new Map((status.held_exercises || []).map(title => [title, name]));
      document.dispatchEvent(new CustomEvent('jointhold'));
    } catch (error) {
      held = new Map();
    }
  }
  function noteFor(title) {
    const name = held.get(title);
    return name ? 'Hold load: ' + name + ' coaching call pending. No increase suggested today.' : null;
  }
  load();
  return {noteFor, load};
})();
