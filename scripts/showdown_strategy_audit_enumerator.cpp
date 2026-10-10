// Research-only exhaustive DK physical-roster enumeration. No database or network.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <vector>
using namespace std;
using Mask=unsigned __int128;
struct P {int salary,csalary,team,pos,actual,eligible,gate,strict,mobile; double mean,p90,obj,prior,qbm,conda,condb;};
struct F {Mask req,cap,abs; vector<array<Mask,3>> counts; double score; int group;};
Mask readmask(istream& in){uint64_t lo,hi;in>>lo>>hi;return Mask(lo)|(Mask(hi)<<64);}
int bits(Mask x){return __builtin_popcountll(uint64_t(x))+__builtin_popcountll(uint64_t(x>>64));}
struct R {array<uint8_t,6> ids; uint8_t cap,teammax,qbs,cpos,gate,strict; double mean,p90; array<double,12> score;};
int main(int argc,char**argv){
 if(argc!=4)return 2; ifstream in(argv[1]); int n;in>>n;vector<P>p(n);
 for(auto&v:p)in>>v.salary>>v.csalary>>v.team>>v.pos>>v.actual>>v.eligible>>v.gate>>v.strict>>v.mobile>>v.mean>>v.p90>>v.obj>>v.prior>>v.qbm>>v.conda>>v.condb;
 vector<vector<double>>pair(n,vector<double>(n)),cp(n,vector<double>(n));vector<double>cu(n);
 for(auto&r:pair)for(auto&v:r)in>>v;for(auto&r:cp)for(auto&v:r)in>>v;for(auto&v:cu)in>>v;
 int nf;in>>nf;vector<F>ft(nf);for(auto&f:ft){f.req=readmask(in);f.cap=readmask(in);f.abs=readmask(in);in>>f.score>>f.group;int nc;in>>nc;for(int i=0;i<nc;i++){Mask m=readmask(in);int lo,hi;in>>lo>>hi;f.counts.push_back({m,Mask(lo),Mask(hi)});}}
 if(!in)return 3;
 vector<uint64_t>hist(200001);array<double,12>bm{},bp{},bs{};array<double,12>mp{},pm{};array<double,12>variantmax{};array<int,6>a{}; uint64_t total=0,structural=0,retained=0;double oracle=-1e30;Mask optcapt=0;
 ofstream out(argv[2],ios::binary);int pass=0;
 auto visit=[&](int salary,int actual,int t0,Mask mask){
   if(t0==0||t0==6)return;int tm=max(t0,6-t0);bool ok=true,gate=true,strict=true;int qb[2]={},pc[2]={},qc=0;
   double mean=0,p90=0,obj=0,pa=0,pb=0;
   for(int j:a){auto&v=p[j];ok &= v.eligible;gate &= v.gate;strict &= v.strict;if(v.pos==0){qb[v.team]++;qc++;}if(v.pos==2||v.pos==3)pc[v.team]++;mean+=v.mean;p90+=v.p90;obj+=v.obj;pa+=v.conda;pb+=v.condb;}
   // Candidate legality reproduces the production hard QB rules; the DK denominator does not.
   ok &= qc>=1&&qc<=2;for(int t=0;t<2;t++)if(pc[t]>=2&&qb[t]==0)ok=false;
   array<double,5>corr{};double pairs=0; if(ok){for(int i=0;i<6;i++)for(int j=i+1;j<6;j++)pairs+=pair[a[i]][a[j]];
    for(int j:a)if(p[j].pos==0){double m=p[j].qbm;int t=p[j].team;corr[0]+=.6*m*(pc[t]>=1);corr[1]+=.3*m*(pc[t]>=2)+.1*m*(pc[t]>=3);corr[2]+=.45*m*(pc[1-t]>=1);}}
   for(int c:a){auto&v=p[c];if(salary+v.csalary-v.salary>50000)continue;
    if(pass==0){int score=actual+v.actual; // actual input is points*100; doubled lineup points are exact half cents.
      int ix=score+20000;if(ix<0||ix>=int(hist.size())){cerr<<"histogram range";exit(4);}hist[ix]++;total++;
      if(score>oracle){oracle=score;optcapt=Mask(1)<<c;}else if(score==oracle)optcapt|=Mask(1)<<c;
    }
    if(!ok)continue;if((v.pos==2||v.pos==3)&&!qb[v.team])continue;if(v.pos==0&&pc[v.team]<(v.mobile?1:2))continue;
    if(pass==0)structural++;
    double m=mean+.5*v.mean,z=p90+.5*v.p90;double sc=obj-v.obj+1.5*v.obj*v.prior;
    auto cr=corr;cr[4]=pairs+cu[c];for(int j:a)if(j!=c)cr[4]+=cp[c][j];
    Mask cm=Mask(1)<<c;
    for(auto&f:ft){if((mask&f.req)!=f.req||(cm&f.cap)!=f.cap||(mask&f.abs))continue;bool active=true;for(auto&ct:f.counts){int count=bits(mask&ct[0]);if(count<int(ct[1])||count>int(ct[2])){active=false;break;}}if(active)cr[f.group]+=f.score;}
    double cor=0;for(double x:cr)cor+=x;sc+=cor;
    double prioradd=1.5*v.obj*(v.prior-1);
    array<double,12>s={sc,sc-prioradd,sc-prioradd*(1-.15/.35),sc-(v.pos==0?min(0.0,prioradd)*min(1.0,max(0.0,(v.mobile?1.0:0.0))):0),sc-cor,sc-cr[0],sc-cr[1],sc-cr[2],sc-cr[3],sc-cr[3]-cr[4],pa+.5*v.conda,pb+.5*v.condb};
    if(pass==0){if(gate){for(int k=0;k<12;k++){variantmax[k]=max(variantmax[k],s[k]);int t=3+k/4;int pol=k%4; // k also indexes team/QB construction policy below.
       bool allowed=tm<=t && (!(pol&1)||qc<=1)&&(!(pol&2)||v.pos!=0);if(!allowed)continue;
       if(m>bm[k]){bm[k]=m;mp[k]=z;}if(z>bp[k]){bp[k]=z;pm[k]=m;}bs[k]=max(bs[k],sc);}}
    }else{bool keep=false;for(int k=0;k<12;k++){int t=3+k/4,pol=k%4;if(tm>t||((pol&1)&&qc>1)||((pol&2)&&v.pos==0))continue;
      // Exact coverage of all >=93% single/joint/composite screens, 95% selector-regret,
      // and the mean/P90 Pareto frontier: discarded rows are dominated by endpoint witnesses.
      keep|=m>=.90*bm[k]||z>=.90*bp[k]||sc>=.95*bs[k]||!((m<=bm[k]+1e-9&&z<=mp[k]+1e-9)||(m<=pm[k]+1e-9&&z<=bp[k]+1e-9));}
     for(int k=0;k<12;k++)keep|=s[k]>=.95*variantmax[k];if(!keep)continue;
     R row{};for(int i=0;i<6;i++)row.ids[i]=a[i];row.cap=c;row.teammax=tm;row.qbs=qc;row.cpos=v.pos;row.gate=gate;row.strict=strict;row.mean=m;row.p90=z;row.score=s;out.write(reinterpret_cast<char*>(&row),sizeof(row));retained++;
    }
   }
 };
 function<void(int,int,int,int,int,Mask)>loop=[&](int depth,int start,int salary,int actual,int t0,Mask mask){
   if(depth==6){visit(salary,actual,t0,mask);return;}for(int i=start;i<=n-(6-depth);i++){int sal=salary+p[i].salary;if(sal>50000)continue;a[depth]=i;loop(depth+1,i+1,sal,actual+2*p[i].actual,t0+(p[i].team==0),mask|(Mask(1)<<i));}
 };
 loop(0,0,0,0,0,0);pass=1;loop(0,0,0,0,0,0);
 ofstream h(argv[3]);h<<setprecision(17)<<"{\"physical_count\":"<<total<<",\"structural_count\":"<<structural<<",\"retained_count\":"<<retained<<",\"record_bytes\":"<<sizeof(R)<<",\"oracle\":"<<oracle/200<<",\"optimal_captains\":[";bool sep=false;for(int i=0;i<n;i++)if(optcapt&(Mask(1)<<i)){if(sep)h<<",";h<<i;sep=true;}h<<"],\"max_mean\":[";for(int k=0;k<12;k++){if(k)h<<",";h<<bm[k];}h<<"],\"max_p90\":[";for(int k=0;k<12;k++){if(k)h<<",";h<<bp[k];}h<<"],\"max_selector\":[";for(int k=0;k<12;k++){if(k)h<<",";h<<bs[k];}h<<"],\"histogram\":[";sep=false;for(int i=0;i<int(hist.size());i++)if(hist[i]){if(sep)h<<",";h<<"["<<(i-20000)/200.0<<","<<hist[i]<<"]";sep=true;}h<<"]}\n";
 cerr<<"physical="<<total<<" structural="<<structural<<" retained="<<retained<<" bytes="<<sizeof(R)<<"\n";
}
