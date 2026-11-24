#ifndef RTPS_LIVELINESS_STATE_H
#define RTPS_LIVELINESS_STATE_H

namespace rtps {

enum class LivelinessTransition {
  NONE,
  LOST,
  RECOVERED,
};

inline LivelinessTransition evaluateLivelinessTransition(
    bool monitoringEnabled, bool stateInitialized, bool hasActivity,
    bool previousAlive, bool currentAlive) {
  if (!monitoringEnabled || !stateInitialized || !hasActivity ||
      previousAlive == currentAlive) {
    return LivelinessTransition::NONE;
  }
  return previousAlive ? LivelinessTransition::LOST
                       : LivelinessTransition::RECOVERED;
}

}  // namespace rtps

#endif  // RTPS_LIVELINESS_STATE_H
