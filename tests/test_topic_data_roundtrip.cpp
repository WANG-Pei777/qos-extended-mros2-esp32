// Round-trip test: every QoS field serialized into SEDP data must come back
// unchanged through readFromUcdrBuffer, and the parsed data must match the
// original under qosPoliciesCompatible.
#include "rtps/discovery/TopicData.h"
#include "rtps/discovery/QoSCompatibility.h"
#include "ucdr/microcdr.h"
#include <cstdio>
#include <cstring>
static int total=0, failed=0;
static void check(bool c, const char* l){ ++total; if(!c){++failed; std::printf("[FAIL] %s\n",l);} else std::printf("[PASS] %s\n",l); }
int main(){
  rtps::TopicData w;
  std::strcpy(w.topicName,"rt/system_compare"); std::strcpy(w.typeName,"std_msgs::msg::dds_::String_");
  w.reliabilityKind=rtps::ReliabilityKind_t::RELIABLE; w.durabilityKind=rtps::DurabilityKind_t::TRANSIENT_LOCAL;
  w.deadlineSec=0; w.deadlineFraction=0x80000000u;       // 0.5 s
  w.lifespanSec=2; w.lifespanFraction=0;
  w.livelinessSec=1; w.livelinessFraction=0;
  w.historyKind=0; w.historyDepth=10; w.maxSamples=30; w.maxBytes=12288;
  uint8_t buf[1024]; ucdrBuffer out; ucdr_init_buffer(&out,buf,sizeof(buf));
  check(w.serializeIntoUcdrBuffer(out),"serialize succeeds");
  size_t len=ucdr_buffer_length(&out);
  rtps::TopicData r; ucdrBuffer in; ucdr_init_buffer(&in,buf,len);
  check(r.readFromUcdrBuffer(in),"deserialize succeeds");
  check(std::strcmp(r.topicName,w.topicName)==0,"topic name");
  check(std::strcmp(r.typeName,w.typeName)==0,"type name");
  check(r.reliabilityKind==w.reliabilityKind,"reliability");
  check(r.durabilityKind==w.durabilityKind,"durability");
  check(r.deadlineSec==w.deadlineSec && r.deadlineFraction==w.deadlineFraction,"deadline");
  check(r.lifespanSec==w.lifespanSec && r.lifespanFraction==w.lifespanFraction,"lifespan");
  check(r.livelinessSec==w.livelinessSec && r.livelinessFraction==w.livelinessFraction,"liveliness lease");
  check(r.historyKind==w.historyKind && r.historyDepth==w.historyDepth,"history kind+depth");
  check(r.maxSamples==w.maxSamples,"max_samples (standard PID)");
  check(r.maxBytes==0,"max_bytes is not carried over the wire (local only)");
  check(rtps::qosPoliciesCompatible(r,w),"parsed offer compatible with identical request");
  rtps::TopicData req=w; req.deadlineSec=0; req.deadlineFraction=0x40000000u; // requested 0.25 s < offered 0.5 s
  check(!rtps::qosPoliciesCompatible(r,req),"offered deadline 0.5 s does not satisfy requested 0.25 s");
  req=w; req.reliabilityKind=rtps::ReliabilityKind_t::BEST_EFFORT;
  check(rtps::qosPoliciesCompatible(r,req),"Reliable offer satisfies Best Effort request");
  rtps::TopicData be=w; be.reliabilityKind=rtps::ReliabilityKind_t::BEST_EFFORT; be.durabilityKind=rtps::DurabilityKind_t::VOLATILE;
  check(!rtps::qosPoliciesCompatible(be,w),"Best Effort/Volatile offer refused by Reliable/TL request");
  // defaults round trip: infinite durations
  rtps::TopicData d; std::strcpy(d.topicName,"t"); std::strcpy(d.typeName,"T");
  ucdr_init_buffer(&out,buf,sizeof(buf)); check(d.serializeIntoUcdrBuffer(out),"serialize defaults");
  rtps::TopicData d2; ucdr_init_buffer(&in,buf,ucdr_buffer_length(&out)); check(d2.readFromUcdrBuffer(in),"deserialize defaults");
  check(d2.deadlineSec==0x7FFFFFFF && d2.deadlineFraction==0xFFFFFFFF,"infinite deadline survives round trip");
  check(d2.maxSamples==0,"unset max_samples (-1 on the wire) reads back as 0");
  std::printf("TopicData round trip: %d/%d passed\n", total-failed, total);
  return failed?1:0;
}
